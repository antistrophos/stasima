# SPDX-License-Identifier: Apache-2.0
"""
Stasima CAP server — MCP protocol surface over LocalCapStore + the MAP index + the audit log.

Tools give an instance: orient -> author (with envelopes, indexed inline, audit-logged) -> search
-> review its own trail -> propose -> check status -> message peers (read-state in the audit log).

Audit scope: writes (state changes) and failures (what's breaking). Successful reads are observability
and are not logged; read-receipts ARE logged (forensic, write-like). Mutations follow git-first-then-
audit. Identity is the instance's declared name (a deployment binds it from the transport token).
"""
import os
import sys
import time

from mcp.server.fastmcp import FastMCP

from .local_capstore import (LocalCapStore, Identity, PathNotFound, RefNotFound, StaleRef,
                            CapStoreError, PERSP_PREFIX as PERSP, PROP_PREFIX as PROP)
from .map_index import SqliteMapIndex, StubEmbedder, LocalServerEmbedder, index_entry
from .audit_log import SqliteAuditLog
from .authz import Denied, DefaultPolicy
from .entries import compose_entry, parse_entry          # shared content-model serialization
from .orientation import build_orientation               # practice-agnostic machinery + practice slots
from .airlock import Airlock                             # TOTP two-phase remote approval
# canon lifecycle (re-exported here for callers/tests that import via the server module)
from .canon import (LOG_DIR, CHAT_ERA_FREEZE, canon_seq, seq_display, reindex_from_git,
                   land_and_record, validate_log_entry, validate_log_entry as _validate_log_entry,
                   proposal_statuses, close_proposal)


def _transport_security(http_host: str, extra_hosts):
    """DNS-rebinding protection stays ON; the allowlist follows the configured bind. The SDK
    default allows only localhost, which would reject tailnet binds (Host: 100.x...) and
    proxied requests (tailscale serve forwards the .ts.net Host) - so we allow the bind
    address plus any configured proxy hostnames, and nothing else."""
    from mcp.server.transport_security import TransportSecuritySettings
    hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    origins = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]
    for h in [http_host, *extra_hosts]:
        h = h.strip()
        if not h or h in ("127.0.0.1", "localhost", "::1"):
            continue
        hp = h if ":" in h.rsplit("]")[-1] else f"{h}:*"
        hosts.append(hp)
        origins += [f"http://{hp}", f"https://{hp}"]
    return TransportSecuritySettings(enable_dns_rebinding_protection=True,
                                     allowed_hosts=hosts, allowed_origins=origins)


def port_bindings(audit) -> dict:
    """The durable sticky table, derived from append-only port_binding events (latest per port
    wins): {port_token: {"instance": name-or-None, "ts": ts}} — a None instance is a CLEARED port
    (learning re-armed). The audit ledger IS the running config: learning appends, the console
    clears by appending, and the whole rotation history stays readable in order."""
    table = {}
    for e in audit.events(op="port_binding"):
        d = e.get("detail") or {}
        p = d.get("port")
        if not p:
            continue
        if d.get("action") == "clear":
            table[p] = {"instance": None, "ts": e.get("ts")}
        else:
            table[p] = {"instance": e.get("actor"), "ts": e.get("ts")}
    return table


def build_server(store: LocalCapStore, index=None, embedder=None, audit=None, authz=None, airlock=None, *,
                 orientation_text: str = None, orientation_base: str = "technical/orientation",
                 seq_origin: int = CHAT_ERA_FREEZE, deployment_name: str = "",
                 http_host: str = "127.0.0.1", http_port: int = 8787, http_allowed_hosts=(),
                 bound_instance: str = None, binding_mode: str = None,
                 port_token: str = None) -> FastMCP:
    mcp = FastMCP("stasima", host=http_host, port=http_port,   # host/port used only by the http transport
                  transport_security=_transport_security(http_host, http_allowed_hosts))
    has_map = index is not None and embedder is not None

    # Session binding — the SSH-shaped identity pin, with STICKY learning (port-security with
    # sticky MACs; OPERATIONS, "Seat identity"). Sources, strongest first: STASIMA_INSTANCE
    # (pinned — pre-seeded, no learning), a PORT-learned binding (STASIMA_PORT names this
    # definition; the learned name persists as append-only port_binding events in the audit log —
    # the ledger IS the running config, and the console clears it), a SESSION-learned binding
    # (no port: the first identity-claiming WRITE binds this process for its lifetime; the rekey
    # is a new process). Modes (STASIMA_BINDING): strict = mismatched writes refuse — THE DEFAULT:
    # secure unless the server's owner explicitly downgrades; witness = proceed and confess
    # (authored_via in the envelope + an audit row); off = the explicit rip-cord — no learning,
    # no enforcement, the HTTPS-to-HTTP downgrade, server-owned and never callable from the wire.
    # Reads are never guarded (pull model; the corpus is world-readable).
    if bound_instance is not None and not str(bound_instance).strip():
        bound_instance = None
    if port_token is not None and not str(port_token).strip():
        port_token = None
    binding_mode = (binding_mode or "strict").lower()
    if binding_mode not in ("strict", "witness", "off"):
        raise ValueError(f"binding_mode must be strict|witness|off, got {binding_mode!r}")
    _learned = {"name": None, "source": None}   # sticky state: session-held; port-restored below

    def persp_ref(iid): return PERSP + iid
    def prop_ref(pid): return PROP + pid

    def resolve_alias(ref):
        if ref in ("canon", "main"):
            return store.canon_ref
        if ref.startswith("refs/"):
            return ref
        return persp_ref(ref)

    def _authored_envelope(type, title, slug, *, status="active", tags=None, references=None,
                           supersedes=None, superseded_by=None, **extra):
        # the one place an authored entry's envelope is built — kip_commit and propose share it so
        # lineage (references / supersedes / superseded_by) is expressible and identical on both paths
        env = {"type": type, "title": title or slug, "status": status,
               "tags": tags or [], "references": references or []}
        if supersedes:
            env["supersedes"] = supersedes
        if superseded_by:
            env["superseded_by"] = superseded_by
        env.update({k: v for k, v in extra.items() if v})
        return env

    _THREAD_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789-")

    def _check_thread(tag):
        # Ref-safe by construction: a reserved tag must never mint a name the future thread-ref
        # registry (first-open-wins via ref creation, scry via the ref namespace) cannot hold.
        # Lowercase alnum + hyphens, starts alphanumeric, max 64. The VALUE semantics stay unruled
        # (reserve-the-field-rule-the-values); only the form is structure.
        if not tag or len(tag) > 64 or tag[0] == "-" or not set(tag) <= _THREAD_CHARS:
            raise Denied(f"thread= must be a ref-safe tag (lowercase a-z, 0-9, hyphens; starts "
                         f"alphanumeric; max 64), got {tag!r} — the tag becomes a ref name when the "
                         f"thread registry lands, and a form it cannot hold would poison the reservation")

    def _name_collision(name):
        """An existing perspective whose name case-insensitively equals `name` but differs in exact
        casing — a drift that would FORK identity, since names are case-sensitive everywhere in v1
        (perspective ref, inbox recipient, cursor). Returns the existing canonical name, or None.
        (Full case-normalization lands with identity-binding in 1.1; this is the v1 loud-not-silent guard.)"""
        low = name.casefold()
        for r in store.list_refs(PERSP):
            existing = r.name[len(PERSP):]
            if existing != name and existing.casefold() == low:
                return existing
        return None

    def _commit_retry(ref, path, build, author, op_id):
        # `build(tip)` -> {path: content-str}, composed FRESH per CAS attempt so all per-tip work —
        # the mechanical pins, the immutability guard, the fold's reuse guard — is keyed to the very
        # oid passed as expected_parent. A StaleRef retry therefore re-runs guards and re-pins against
        # the new tip; nothing stamped or checked against a superseded tip can survive into the commit.
        # A multi-file build is the atomic-fold carrier: entry and vantage land together or not at all.
        if ref.startswith(PERSP):
            clash = _name_collision(author)
            if clash:
                _log(author, "name_collision", target_ref=ref, outcome="denied", detail={"existing": clash})
                raise Denied(f"a perspective '{clash}' already exists; '{author}' differs only in case "
                             f"and would FORK your identity (names are case-sensitive in v1). "
                             f"Re-announce as '{clash}' and use it consistently — one name, forever.")
        for attempt in range(2):
            tip = store.resolve_ref(ref)
            changes = {p: c.encode() for p, c in build(tip).items()}
            try:
                return store.commit(ref, changes, f"KIP {path}",
                                    Identity(author), expected_parent=tip, op_id=op_id)
            except StaleRef:
                if attempt == 1:
                    raise

    def _index(ref, path, is_canon, author, oid, envelope, body):
        if has_map:
            index_entry(index, embedder, ref=ref, path=path, is_canon=is_canon,
                        authoring_instance=author, content_oid=oid, envelope=envelope, body=body)

    def _log(actor, op, **kw):
        if audit is not None:
            audit.append(actor, op, **kw)

    def _authz(actor, op, ref=None, path=None):
        if authz is None:
            return
        try:
            authz.check(actor, op, ref, path)
        except Denied as e:
            _log(actor, op, target_ref=ref, target_path=path, outcome="denied", detail={"msg": str(e)})
            raise

    def _check_binding(claimed, op, ref=None, path=None):
        """Identity-claiming WRITES check their claimed name against this connection's binding —
        pinned (env), port-learned (durable sticky), or session-learned (the first write binds).
        Returns the witness stamp ({'authored_via': <bound name>}) when the caller should stamp an
        envelope, else None. Every witness mismatch leaves an audit row here regardless of whether
        the op writes an envelope — the confession is never optional, only its git copy is."""
        if binding_mode == "off":
            return None                                    # the explicit, server-owned rip-cord
        bound = bound_instance or _learned["name"]
        if bound is None:
            # sticky learn: the first identity-claiming write binds this connection — and, through
            # a port, the definition (durably: the learn is an append-only event the console clears)
            _learned.update(name=claimed, source="port" if port_token else "session")
            detail = {"mode": binding_mode, "source": _learned["source"], "learned": True}
            if port_token:
                detail["port"] = port_token
                _log(claimed, "port_binding", detail={"port": port_token, "action": "learn",
                                                      "mode": binding_mode})
            _log(claimed, "session_binding", detail=detail)
            return None
        if claimed == bound:
            return None
        if binding_mode == "strict":
            how = "pinned to" if bound_instance else "learned (sticky) as"
            _log(claimed, op, target_ref=ref, target_path=path, outcome="denied",
                 detail={"reason": "session-binding mismatch", "bound": bound})
            raise Denied(f"this connection is {how} '{bound}' (strict). To act as '{claimed}': use "
                         f"that seat's own connection, or the practitioner downgrades this "
                         f"definition (STASIMA_BINDING=witness, or a console `binding --clear` on "
                         f"its port) — the downgrade is server-owned by design; there is no "
                         f"in-call override")
        _log(claimed, op, target_ref=ref, target_path=path, outcome="witness",
             detail={"bound": bound})
        return {"authored_via": bound}

    if bound_instance is not None:
        # the binding declaration enters the append-only record at every spawn — rekeys (env edit +
        # restart) therefore leave a rotation trail the practitioner can read back
        _log(bound_instance, "session_binding", detail={"mode": binding_mode, "source": "pinned"})
    elif port_token is not None and audit is not None and binding_mode != "off":
        # durable sticky: restore this port's learned binding from the ledger (latest event wins;
        # a cleared port re-arms learning)
        _prior = port_bindings(audit).get(port_token, {}).get("instance")
        if _prior:
            _learned.update(name=_prior, source="port")
            _log(_prior, "session_binding", detail={"mode": binding_mode, "source": "port",
                                                    "port": port_token, "restored": True})

    def _exists(ref, path):
        try:
            store.read_blob(ref, path)
            return True
        except (PathNotFound, RefNotFound):
            return False

    def _canon_cursor(actor):
        # the canon oid the instance last pulled — a server-tracked audit fact, not a self-claim
        if audit is None:
            return None
        evs = audit.events(actor=actor, op="canon_pull")
        return evs[-1]["result_oid"] if evs else None

    def _pin(envelope, instance_id, tip):
        """The mechanical two-clock pin, stamped on EVERY write: the author's canon cursor
        (`canon_state`, server-sourced — the shared primitive VAP introduced) and the target ref's
        commit position (`instance_depth`, parent-count+1 — monotonic per ref, survives a reindex
        because it rides the envelope). Deliberately NOT the declared personal label: the clock
        sweep proved the seq is a declared, social fact the server must never pretend to derive.
        `tip` is the CAS attempt's expected_parent — pin and precondition share one oid, so a retry
        re-pins. A parentless first commit is depth 1 (no fallback: a fresh perspective is BORN at 1;
        a proposal branch is created from canon before its first commit, so its tip already exists).
        Both faces of an atomic fold share one commit, hence one depth."""
        envelope.setdefault("canon_state", _canon_cursor(instance_id) or "")
        envelope["instance_depth"] = (store.commit_count(tip) + 1) if tip else 1
        return envelope

    def _blob_at(tip, path):
        # the blob at `path` in commit `tip`'s tree, or None — the tip-keyed read the guards use
        if tip is None:
            return None
        try:
            return store.read_blob_at(tip, path)
        except (PathNotFound, RefNotFound):
            return None

    def _check_immutable(actor, tip, path, new_body):
        # bodies are immutable; a same-path write with a different body must supersede to a new slug.
        # Keyed to the CAS attempt's tip (not the live ref): the guard's conclusion and the commit's
        # precondition hold on the SAME oid, so a concurrent commit cannot slip a body change between
        # the check and the write — the CAS fails instead, and the retry re-runs this guard.
        old = _blob_at(tip, path)
        if old is not None:
            old_body = parse_entry(old.decode("utf-8", "replace"))[1]
            if old_body.strip() != new_body.strip():
                _log(actor, "kip_commit", target_path=path, outcome="denied",
                     detail={"reason": "body immutable; supersede to a new slug"})
                raise Denied(f"{path} exists and an entry's body is immutable — supersede to a new slug")

    def _check_not_staged(proposal_id):
        # a staged proposal is frozen for review — the airlock's chamber must hold exactly what was staged
        if airlock is not None and airlock.state(proposal_id)["state"] == "staged":
            raise Denied(f"proposal {proposal_id} is frozen for review (staged) — land, revert, or let it expire")

    def _closed_reason(proposal_id):
        # a proposal's closure is its tip commit's `close:` subject — terminal for SEAT operations
        # only (the gate stays sovereign: the practitioner may still land or discard anything)
        sub = store.tip_subject(prop_ref(proposal_id))
        return sub[len("close: "):] if sub.startswith("close: ") else None

    def _check_not_closed(proposal_id):
        reason = _closed_reason(proposal_id)
        if reason is not None:
            raise Denied(f"proposal {proposal_id} is closed ({reason}) — closed is terminal for seats; "
                         f"open a fresh proposal (the gate may still land or discard the closed one)")

    def _attention():
        # count of unread practitioner-recipient messages; delivery is conduct-convention, this is just the field
        if not has_map or audit is None:
            return None
        return len([m for m in index.inbox("practitioner") if not audit.is_read("practitioner", m.path)])

    def _require_reconciled(actor):
        # reaching into shared space (propose) requires you've reconciled with CURRENT canon first
        if audit is None:
            return
        tip = store.resolve_ref(store.canon_ref)
        if tip is None:
            return
        if not _exists(persp_ref(actor), f"state/reconciled-{tip[:12]}.md"):
            _log(actor, "propose", target_ref=store.canon_ref, outcome="denied",
                 detail={"reason": "not reconciled with current canon", "canon_tip": tip})
            raise Denied(f"reconcile with current canon {tip[:12]} first (canon_diff, then sup_reconcile)")

    def _orientation():
        # static override if provided (e.g. tests); otherwise render machinery + practice slots from canon
        return orientation_text if orientation_text else build_orientation(
            store, base=orientation_base, deployment_name=deployment_name)

    # ---------------------------------------------------------------- orient
    @mcp.tool()
    def announce(instance_id: str) -> dict:
        """Announce presence; returns orientation + current canon head + your perspective tip."""
        home = deployment_name or "Stasima"
        out = {"welcome": f"Welcome to {home}, {instance_id}.", "orientation": _orientation(),
               "canon_head": store.resolve_ref(store.canon_ref),
               "your_perspective_tip": store.resolve_ref(persp_ref(instance_id)),
               "practitioner_attention": _attention()}
        clash = _name_collision(instance_id)   # surface a fork-by-casing on arrival, before any write
        if clash:
            out["name_warning"] = (f"a perspective '{clash}' already exists and '{instance_id}' differs "
                                   f"only in case — writing under '{instance_id}' would fork your identity. "
                                   f"Use '{clash}'. (Names are case-sensitive in v1; writes will be refused.)")
        return out

    # (0.1.5 dedup: `orientation` and `canon_head` removed — the former was one field of announce's
    # return, the latter a strict subset of canon_state. One home per fact.)

    @mcp.tool()
    def whoami(instance_id: str) -> dict:
        """How the server sees you — always including this connection's session binding (the
        SSH-shaped identity pin with sticky learning; see OPERATIONS): mode, the bound name (pinned,
        port-restored, or learned from your first write — null if nothing has bound yet), its
        source, and whether YOUR claim matches. Mode `off` is the server-owned downgrade, shown
        plainly — like http:// in the address bar."""
        out = {"instance_id": instance_id, "perspective_ref": persp_ref(instance_id),
               "namespace": f"perspectives/{instance_id}", "allowed_ops": ["kip_commit", "propose", "imp_send", "vap_record"],
               "note": "identity is a recorded name; the session binding (transport-pinned or sticky-learned) guards writes"}
        eff = bound_instance or _learned["name"]
        sb = {"mode": binding_mode, "bound_instance": eff,
              "source": "pinned" if bound_instance else _learned["source"],
              "match": (instance_id == eff) if eff else None}
        if port_token:
            sb["port"] = port_token
        out["session_binding"] = sb
        return out

    # ---------------------------------------------------------------- author
    @mcp.tool()
    def kip_commit(instance_id: str, domain: str, slug: str, body: str, op_id: str,
                   title: str = "", type: str = "kno",
                   tags: list[str] | None = None, references: list[str] | None = None,
                   supersedes: list[str] | None = None, status: str = "active",
                   superseded_by: list[str] | None = None,
                   horizon: str = "", horizon_title: str = "", tick: str = "",
                   thread: str = "") -> dict:
        """Author an entry to your append-only perspective at <domain>/<slug>.md (YAML envelope +
        body). Revise by SUPERSESSION, never edit: the new entry carries supersedes=[<old>]; retire
        the old with a same-body re-commit, status='superseded' + superseded_by=[<new>]. `tick=<hex>`
        (state/ entries only) mirrors your DECLARED clock label — surfaced, never validated.
        `thread=<ref-safe-tag>` declares associative work. `horizon=` is THE FOLD: the entry and its
        confirmed vantage in ONE atomic commit under one op_id (no horizon = no vantage, honestly).
        The deep teaching lives in the current suite's author dock."""
        ref = persp_ref(instance_id)
        path = f"{domain}/{slug}.md"
        _authz(instance_id, "kip_commit", ref, path)
        _binding_stamp = _check_binding(instance_id, "kip_commit", ref, path)
        if tick:
            # form + scope are structure (the shapes accepted at write); the VALUE is the seat's —
            # never compared to prose or counted against history (declarations govern)
            tick = tick.lower().lstrip(":")
            if domain != "state":
                raise Denied("tick= rides state updates only (two-clock conventions v3, clause 5) — "
                             "declare the tick on a state/ entry, or drop the field")
            try:
                int(tick, 16)
            except ValueError:
                raise Denied(f"tick= must be a hex seq (e.g. '1a' — lowercase, no '::'), got {tick!r}")
        if thread:
            _check_thread(thread)
        envelope = _authored_envelope(type, title, slug, status=status, tags=tags, references=references,
                                      supersedes=supersedes, superseded_by=superseded_by, tick=tick,
                                      thread=thread or None)
        if _binding_stamp:
            envelope.update(_binding_stamp)
        vap_path = f"vantages/{op_id}-vap.md" if horizon else None
        vap_holder = {}

        def build(btip):
            # per-tip work, re-run on a CAS retry: guard + pins + composition all keyed to `btip`
            _check_immutable(instance_id, btip, path, body)
            _pin(envelope, instance_id, btip)
            changes = {path: compose_entry(envelope, body)}
            if horizon:
                # confirmed-by-construction: the folded entry is necessarily the author's own, recorded
                # at the true moment — dignity and temporal guards are satisfied by the call shape.
                # The vantage path derives from op_id; reusing an op_id after the ref moved on would
                # silently REWRITE the recorded standpoint — refuse it (a replay of the same op is
                # fine: the tip's own op-id matches and the store returns the prior commit unwritten).
                if _blob_at(btip, vap_path) is not None and store.commit_op_id(btip) != op_id:
                    _log(instance_id, "kip_commit", target_path=vap_path, op_id=op_id, outcome="denied",
                         detail={"reason": "op_id reuse would rewrite a recorded vantage"})
                    raise Denied(f"{vap_path} already records a vantage under op_id '{op_id}' — an op_id "
                                 f"names one act; use a new op_id (the standpoint record is append-only)")
                vap_env = {"type": "vap", "title": horizon_title or f"vantage on {path}", "status": "active",
                           "vantage": "confirmed", "canon_state": envelope["canon_state"],
                           "instance_depth": envelope["instance_depth"],   # one commit, one depth — both faces
                           "coordinates": [path]}
                vap_holder["env"] = vap_env
                changes[vap_path] = compose_entry(vap_env, horizon)
            return changes

        try:
            r = _commit_retry(ref, path, build, instance_id, op_id)
        except CapStoreError as e:
            _log(instance_id, "kip_commit", target_ref=ref, target_path=path, op_id=op_id,
                 outcome=f"error:{e.__class__.__name__}", detail={"msg": str(e)})
            raise
        out = {"oid": r.oid, "ref": r.ref, "path": path, "op_id": r.op_id, "author": instance_id}
        if r.replayed:
            # tip-local idempotency fired: git holds the PRIOR commit, nothing was written this call.
            # Do not index and do not report content this call composed — report what git actually holds.
            _log(instance_id, "kip_commit", target_ref=ref, target_path=path, op_id=op_id,
                 result_oid=r.oid, detail={"replayed": True})
            out["replayed"] = True
            if vap_path:
                if _exists(ref, vap_path):
                    out["folded"] = {"path": vap_path, "vantage": "confirmed", "replayed": True}
                else:
                    out["note"] = ("replayed the prior commit for this op_id — it carried no vantage; "
                                   "to fold, author under a new op_id")
            return out
        _index(ref, path, False, instance_id, r.oid, envelope, body)            # git-first ...
        detail = {"folded": vap_path} if vap_path else None
        _log(instance_id, "kip_commit", target_ref=ref, target_path=path, op_id=op_id, result_oid=r.oid,
             detail=detail)                                                     # ... then audit
        if vap_path:
            vap_env = vap_holder["env"]
            _index(ref, vap_path, False, instance_id, r.oid, vap_env, horizon)
            out["folded"] = {"path": vap_path, "vantage": "confirmed", "canon_state": vap_env["canon_state"]}
        return out

    # ---------------------------------------------------------------- read
    @mcp.tool()
    def kip_get(ref: str, path: str, resolve: str = "live", with_vantages: bool = False) -> dict:
        """Read an entry (envelope + body in `text`). `ref`: 'canon', a seat name, or a full ref.
        resolve='live' (default) follows supersession to the LIVING edition (redirects shown in
        `resolved_from`); resolve='exact' reads the edition at the path as-is. A miss names the
        ref(s) actually holding the path. with_vantages=true also returns the bound vantages in
        full."""
        full = resolve_alias(ref)
        p = path if path.endswith(".md") else path + ".md"
        try:
            text = store.read_blob(full, p).decode()
        except (PathNotFound, RefNotFound):
            # tolerant miss: say where it DOES resolve rather than a blind not-found — the error is
            # the instruction; content never silently crosses refs (attribution stays deliberate)
            found = []
            for cand in [store.canon_ref] + [r.name for r in store.list_refs(PERSP)]:
                if cand == full:
                    continue
                try:
                    store.read_blob(cand, p)
                    found.append("canon" if cand == store.canon_ref else cand[len(PERSP):])
                except (PathNotFound, RefNotFound):
                    pass
            hint = f" — but it exists on ref(s) {found}; fetch it there explicitly" if found else ""
            raise PathNotFound(f"{p} not found at {ref}{hint}")
        chain = []
        while resolve != "exact" and len(chain) < 10:
            envelope, _body = parse_entry(text)
            succ = envelope.get("superseded_by") or []
            if envelope.get("status") != "superseded" or not succ:
                break
            nxt = succ[0] if succ[0].endswith(".md") else succ[0] + ".md"
            if nxt == p or nxt in chain:
                break                                    # cycle guard: stop, chain stays visible
            try:
                text2 = store.read_blob(full, nxt).decode()
            except (PathNotFound, RefNotFound):
                break                                    # follow failed: return the last edition that resolves
            chain.append(p)
            p, text = nxt, text2
        envelope, _body = parse_entry(text)
        out = {"text": text, "path": p, "status": envelope.get("status", ""), "title": envelope.get("title", "")}
        if chain:
            out["resolved_from"] = chain
        if with_vantages:
            vs = index.vantages_for(entry=p) if index is not None else []
            out["vantages"] = [{"path": v.path, "ref": v.ref, "author": v.authoring_instance,
                                "vantage": v.vantage, "canon_state": v.canon_state, "title": v.title,
                                "horizon": v.body_text} for v in vs]
        return out

    def _listing(full_ref: str, paths: list) -> list:
        """Enrich bare paths into triageable pointers ({path, title, status, type}) from the index —
        ONE query, not N per-path git reads. Git remains the truth of WHICH paths exist; a path the
        index doesn't know (e.g. a proposal ref, or a stale index) keeps empty fields rather than lying."""
        env = index.envelopes_for(full_ref) if index is not None else {}
        blank = {"title": "", "status": "", "type": ""}
        return [{"path": p, **env.get(p, blank)} for p in paths]

    @mcp.tool()
    def list_entries(ref: str, path: str = "") -> dict:
        """List entries under a ref ('canon', an instance name, or a full ref) as triageable pointers —
        each carries path, title, status, and type, so live-vs-dead and what's-what are apparent
        BEFORE you pull a body."""
        full = resolve_alias(ref)
        return {"entries": _listing(full, store.list_paths(full, path))}

    # (0.1.5 dedup: `my_perspective` removed — list_entries(ref=<your name>) is the same listing;
    # your tip rides announce and sup_state.)

    @mcp.tool()
    def kip_history(ref: str, path: str) -> dict:
        """Version trail for an entry (newest first): oid, author, subject, title — the pointer
        grammar extends to trails, so a version is recognizable without fetching its body."""
        r = resolve_alias(ref)
        p = path if path.endswith(".md") else path + ".md"
        hist = store.history(r, p)
        for h in hist:
            try:
                env, _ = parse_entry(store.read_blob_at(h["oid"], p).decode("utf-8", "replace"))
                h["title"] = env.get("title", "")
            except (PathNotFound, RefNotFound):
                h["title"] = ""
        return {"history": hist}

    # ---------------------------------------------------------------- propose + track
    @mcp.tool()
    def propose(instance_id: str, proposal_id: str, domain: str, slug: str, body: str, op_id: str,
                title: str = "", type: str = "kno", seq: str = "",
                tags: list[str] | None = None, references: list[str] | None = None,
                supersedes: list[str] | None = None, status: str = "active",
                superseded_by: list[str] | None = None, origin_author: str = "",
                thread: str = "") -> dict:
        """Open or extend a proposal targeting canon at <domain>/<slug>.md — only the practitioner
        lands. Reconcile first. Every proposal needs exactly ONE log entry to land:
        propose(domain='meta/log', slug='<seq>', type='log', seq='<seq>'), seq = canon_state's
        next_seq (checked here, fail-fast). Carrying ANOTHER seat's work (their path, or a verbatim
        body) requires origin_author=<seat> — silent reattribution is refused; the gate sees both
        names. `thread=` on the log entry tags the whole land. Lineage fields match kip_commit.
        The deep teaching lives in the current suite's author dock."""
        ref = prop_ref(proposal_id)
        path = f"{domain}/{slug}.md"
        _authz(instance_id, "propose", ref, path)
        _binding_stamp = _check_binding(instance_id, "propose", ref, path)
        _check_not_staged(proposal_id)
        _check_not_closed(proposal_id)
        _require_reconciled(instance_id)
        if domain.rstrip("/") == "meta/log":
            # fail-fast at the seat that can fix it: without this, a malformed log entry sails
            # through propose and the guard fires at LAND — making the practitioner the error-relay
            # for a defect only the proposer can repair (Lintel's soak finding)
            s = (seq or "").lower()
            try:
                int(s, 16)
            except ValueError:
                raise Denied(f"a meta/log entry needs `seq` as lowercase hex at propose-time (got {seq!r}) "
                             f"— canon_state shows next_seq; the land would refuse this later, so refuse it here")
            if slug.lower() != s:
                raise Denied(f"log slug {slug!r} must equal its seq {s!r} (the entry lands at meta/log/<seq>.md)")
        if index is not None:
            # the cross-propose attribution guard: carrying another seat's work toward canon is a
            # legitimate flow (curation) — carrying it SILENTLY is not. Two axes, both facts: the
            # path already under another name, or the verbatim body anywhere. Refusing silence is
            # structure; judging paraphrase-credit stays usage (meta/machinery-structure-instance-usage).
            matched = {}                                     # author -> exemplar path
            for a in index.authors_of(path):
                if a and a != instance_id:
                    matched.setdefault(a, path)
            for a, p in index.authors_of_body(body).items():
                if a and a != instance_id:
                    matched.setdefault(a, p)
            if matched and not origin_author:
                who = "; ".join(f"{a} ({p})" for a, p in sorted(matched.items()))
                _log(instance_id, "propose", target_ref=ref, target_path=path, outcome="denied",
                     detail={"reason": "cross-propose without origin_author", "matched": sorted(matched)})
                raise Denied(f"this content already exists under another seat's name — {who}. Carrying "
                             f"another's work toward canon requires origin_author=<seat> (attribution "
                             f"rides the envelope; the practitioner sees both names at the gate). "
                             f"Silent reattribution is refused.")
            if origin_author and matched and origin_author not in matched:
                raise Denied(f"origin_author={origin_author!r} contradicts the record that triggered the "
                             f"guard — the matched author(s): {sorted(matched)}. Name the seat the content "
                             f"actually belongs to.")
        if thread:
            _check_thread(thread)
        envelope = _authored_envelope(type, title, slug, status=status, tags=tags, references=references,
                                      supersedes=supersedes, superseded_by=superseded_by,
                                      seq=seq.lower() if seq else None,
                                      origin_author=origin_author or None,
                                      thread=thread or None)
        if _binding_stamp:
            envelope.update(_binding_stamp)

        def build(btip):
            _pin(envelope, instance_id, btip)
            return {path: compose_entry(envelope, body)}
        try:
            if store.resolve_ref(ref) is None:
                store.create_branch(ref, store.resolve_ref(store.canon_ref))
            r = _commit_retry(ref, path, build, instance_id, op_id)
        except CapStoreError as e:
            _log(instance_id, "propose", target_ref=ref, target_path=path, op_id=op_id,
                 outcome=f"error:{e.__class__.__name__}", detail={"msg": str(e)})
            raise
        _log(instance_id, "propose", target_ref=ref, target_path=path, op_id=op_id, result_oid=r.oid)
        return {"proposal_id": proposal_id, "oid": r.oid, "path": path, "author": instance_id}

    @mcp.tool()
    def propose_retract(instance_id: str, proposal_id: str, path: str, op_id: str) -> dict:
        """Retract a path from a proposal — e.g. a stale log entry after renumbering (canon advanced,
        so your meta/log/<old-seq>.md must be retracted and re-authored at the new seq). Retraction
        restores ZERO DIVERGENCE: a path canon also holds reverts to canon's current edition; a path
        the proposal added leaves the tree. (It never turns a proposal into a canon-deletion.)"""
        ref = prop_ref(proposal_id)
        _authz(instance_id, "propose", ref, path)
        _check_binding(instance_id, "propose_retract", ref, path)
        _check_not_staged(proposal_id)
        _check_not_closed(proposal_id)
        tip = store.resolve_ref(ref)
        if tip is None:
            raise RefNotFound(ref)
        # retraction is destructive, so the lane is creator-only (adding stays open to all —
        # additions are attributed and reviewed at land; removals erase someone else's work)
        owner = store.branch_creator(ref, store.canon_ref)
        if owner and owner != instance_id:
            _log(instance_id, "propose_retract", target_ref=ref, target_path=path, outcome="denied",
                 detail={"reason": "not the proposal's creator", "owner": owner})
            raise Denied(f"proposal {proposal_id} was opened by {owner} — only its creator may retract from it")
        # Retract = restore ZERO DIVERGENCE for the path, not "delete the path": a proposal that
        # MODIFIED a canon path reverts to canon's current edition — deleting it instead would turn
        # the proposal into a canon-deletion the land guard must refuse (Lintel's finding: the model
        # that expected revert was the correct one). A path the proposal ADDED simply leaves the tree.
        try:
            canon_side = store.read_blob(store.canon_ref, path)
        except (PathNotFound, RefNotFound):
            canon_side = None
        r = store.commit(ref, {path: canon_side}, f"retract {path}",
                         Identity(instance_id), expected_parent=tip, op_id=op_id)
        _log(instance_id, "propose_retract", target_ref=ref, target_path=path, op_id=op_id,
             result_oid=r.oid, detail={"reverted_to_canon": canon_side is not None})
        return {"proposal_id": proposal_id, "retracted": path, "oid": r.oid}

    # (0.1.5 dedup: `proposal_status` removed — it ran the pre-lifecycle is-ancestor logic and gave
    # strictly poorer answers than list_proposals' statuses; the deep look stays conflict_preview.)

    @mcp.tool()
    def conflict_preview(proposal_id: str) -> dict:
        """Would this proposal merge cleanly into canon right now? Read-only; creates no candidate.
        `removes` is the one to watch: landing a proposal that removes a canon path is REFUSED
        (canon is append-only). If `removes` is non-empty, re-author before asking to land.
        `attributions` lists entries carried on ANOTHER seat's behalf ({path: {authored, proposed}})
        — the gate sees both names wherever origin_author was declared."""
        summary = store.preview_merge(prop_ref(proposal_id))
        pref = prop_ref(proposal_id)
        attributions = {}
        for p in summary.changed_paths:
            try:
                env, _ = parse_entry(store.read_blob(pref, p).decode("utf-8", "replace"))
            except (PathNotFound, RefNotFound):
                continue
            if env.get("origin_author"):
                hist = store.history(pref, p)
                attributions[p] = {"authored": env["origin_author"],
                                   "proposed": hist[0]["author"] if hist else ""}
        conflicted = bool(summary.conflicts)
        return {"conflicts": conflicted, "conflict_detail": summary.conflicts,
                "changed_paths": summary.changed_paths,
                "adds": summary.added, "removes": summary.removed, "modifies": summary.modified,
                # on a clean preview the delta is canon-relative (the candidate); on a conflicted one
                # it is the proposal's own changes since branching — shown so a conflict never hides
                # the delta, but a canon-removal claim is only meaningful on the candidate basis
                "delta_basis": "proposal-since-base" if conflicted else "candidate",
                "would_remove_canon": bool(summary.removed) and not conflicted,
                "attributions": attributions}

    @mcp.tool()
    def perf_scry() -> dict:
        """The server-git boundary, measured since this server spawned — SCRY-grade (changes nothing,
        no hinge). Per-git-verb subprocess counts, total/avg/max wall-clock: every git crossing flows
        through one chokepoint, so this is the boundary's COMPLETE ledger. Read it before and after a
        heavy act (a land, a first-pull reconcile, a listing sweep) and the delta names what that act
        actually cost. On this substrate each git call is a process spawn with a fixed floor — a verb
        that is hot by COUNT wants batching; hot by MAX wants an algorithmic look."""
        return store.perf_stats()

    @mcp.tool()
    def propose_close(instance_id: str, proposal_id: str, reason: str, op_id: str) -> dict:
        """Close a proposal — the terminal verb for staging that will not land: superseded by a fresh
        proposal, dead against current canon, or simply done with. Writes a `close:` tombstone commit
        (the ref and its history remain; nothing is deleted). Terminal for SEAT operations only —
        propose and retract refuse a closed proposal; the gate stays sovereign and may still land or
        discard it. Creator-only, plus the practitioner's configured approvers (clearing lingering
        offerings is the gate's own duty)."""
        ref = prop_ref(proposal_id)
        _authz(instance_id, "propose", ref, f"close/{proposal_id}")
        _check_binding(instance_id, "propose_close", ref, f"close/{proposal_id}")
        _check_not_staged(proposal_id)
        tip = store.resolve_ref(ref)
        if tip is None:
            raise RefNotFound(ref)
        owner = store.branch_creator(ref, store.canon_ref)
        if owner and owner != instance_id and instance_id not in store.approvers:
            _log(instance_id, "propose_close", target_ref=ref, outcome="denied",
                 detail={"reason": "not the proposal's creator", "owner": owner})
            raise Denied(f"proposal {proposal_id} was opened by {owner} — only its creator (or a "
                         f"configured approver) may close it")
        return close_proposal(store, audit, proposal_id, reason, instance_id, op_id=op_id)

    @mcp.tool()
    def list_proposals() -> dict:
        """Proposal ids plus their lifecycle: `statuses` maps each id to open | landed | closed
        (with `closed_reason`), and open proposals carry `lands_behind` — how many lands canon has
        taken since the proposal branched (the mechanical staleness fact, surfaced raw; whether a
        lingering proposal is DUE for closing is judgment, so no threshold is baked in). Whether an
        open proposal would merge cleanly stays conflict_preview's question — a listing is bearings,
        not an examination."""
        ids = [r.name[len(PROP):] for r in store.list_refs(PROP)]
        return {"proposals": ids, "statuses": proposal_statuses(store)}

    @mcp.tool()
    def list_instances() -> dict:
        """The roster: every seat holding a perspective, wrapped in a named object (a bare list can
        fuse names on the wire; attribution must survive it). With the audit log present,
        `current_with_canon` maps each seat to whether its reconcile cursor sits at canon's tip —
        presence and currency in one glance (absorbs 0.1.4's sup_who)."""
        names = [r.name[len(PERSP):] for r in store.list_refs(PERSP)]
        out = {"instances": names}
        if audit is not None:
            canon_tip = store.resolve_ref(store.canon_ref)
            out["current_with_canon"] = {n: _canon_cursor(n) == canon_tip for n in names}
        return out

    # ---------------------------------------------------------------- MAP (needs an index) + IMP (needs an index + audit)
    if has_map:
        @mcp.tool()
        def map_search(instance_id: str, query: str, scope: str = "all",
                       type: str | None = None, limit: int = 10,
                       include_superseded: bool = False, include_weak: bool = False) -> dict:
            """Semantic search over the corpus, attributed — pointers (path/ref/author/type/title/
            status/score/preview), never an unattributed blend. scope: canon | mine | all. Live-only
            by default (`include_superseded=true` opts in; every hit carries status). Weak hits below
            the embedder's calibrated floor are withheld WITH a count (`below_floor` — an empty
            result is never silent); `include_weak=true` returns them."""
            qv = embedder.embed_query([query])[0]
            hits = index.search(qv, scope=scope, instance_id=instance_id, type=type, limit=limit,
                                status=None if include_superseded else "active")
            floor = getattr(embedder, "score_floor", 0.0) or 0.0
            weak = [h for h in hits if h.score < floor]
            if weak and not include_weak:
                hits = [h for h in hits if h.score >= floor]
            return {"results": [{"path": h.path, "ref": h.ref, "author": h.authoring_instance, "is_canon": h.is_canon,
                     "type": h.type, "title": h.title, "status": h.status, "score": h.score,
                     "preview": h.preview} for h in hits],
                    "below_floor": 0 if include_weak else len(weak)}

        @mcp.tool()
        def thread_scry(thread: str = "", limit: int = 16, offset: int = 0) -> dict:
            """Bearings on declared threads — SCRY-grade: coordination metadata, changes nothing, costs
            no reconcile hinge (fetch, not pull). No argument: the registry view — every declared tag
            with its entry count, authors, and latest pointer. With thread=<tag>: that thread's entries
            as pointers, newest-first, bounded (the hex-page unit). Declared tags only — the value
            semantics are unruled (reserve-the-field-rule-the-values); one tag with surprising authors
            is a curation catch to read, never an error."""
            if not thread:
                return {"threads": index.threads()}
            rows, total = index.thread_entries(thread, limit=limit, offset=offset)
            return {"thread": thread,
                    "entries": [{"path": r.path, "ref": r.ref, "author": r.authoring_instance,
                                 "type": r.type, "title": r.title or r.subject, "status": r.status}
                                for r in rows],
                    "count": len(rows), "total": total,
                    "truncated": offset + len(rows) < total, "offset": offset}

        @mcp.tool()
        def arg_scry(term: str = "") -> dict:
            """The argot dictionary — SCRY-grade (bearings, no reconcile hinge). No argument: the
            registry — every coined term with its distinct-definition count, holding trees, and canon
            presence. With term=<name>: each DISTINCT definition shown once (echo-collapsed), every
            holder annotated (ref, author, status) — one definition across many trees is concordance;
            several definitions under one term is divergence to read, never an error. All editions
            shown WITH status (dictionary-grade honesty). This is the within-practice bore of the
            search-aperture design: collapse and provenance now; the leash parameter arrives
            additively when federation's rails exist."""
            if not term:
                return {"terms": index.arg_terms()}
            t = term.rsplit("/", 1)[-1]
            t = t[:-3] if t.endswith(".md") else t
            defs = index.arg_definitions(t)
            return {"term": t, "definitions": defs, "count": len(defs)}

        if audit is not None:
            @mcp.tool()
            def imp_send(recipients: list[str], subject: str, body: str, op_id: str,
                         instance_id: str = "", sender: str = "",
                         coordinates: list[str] | None = None,
                         supersedes: list[str] | None = None, thread: str = "") -> dict:
                """Author an addressed message — a KIP entry on your branch under messages/, indexed
                into each recipient's inbox. Identity: your seat name as `instance_id` (canonical;
                `sender` is the deprecated 0.1.x twin — pass exactly one). `coordinates` = paths to
                jump to. `supersedes` retires your OWN earlier message(s) — tombstoned in inbox
                views, never hidden. `thread=` chains messages to declared work."""
                who = instance_id or sender
                if not who or (instance_id and sender and instance_id != sender):
                    raise Denied("pass your one seat name as instance_id= (canonical; sender= is its "
                                 "deprecated 0.1.x twin — same meaning, still accepted). Exactly one "
                                 "identity, or both identical.")
                ref = persp_ref(who)
                path = f"messages/{op_id}.md"
                _authz(who, "imp_send", ref, path)
                stamp = _check_binding(who, "imp_send", ref, path)
                if thread:
                    _check_thread(thread)
                envelope = {"type": "msg", "subject": subject, "status": "active",
                            "recipients": recipients, "coordinates": coordinates or []}
                if stamp:
                    envelope.update(stamp)
                if thread:
                    envelope["thread"] = thread
                if supersedes:
                    envelope["supersedes"] = [p if p.endswith(".md") else p + ".md" for p in supersedes]

                def build(btip):
                    _pin(envelope, who, btip)
                    return {path: compose_entry(envelope, body)}
                try:
                    r = _commit_retry(ref, path, build, who, op_id)
                except CapStoreError as e:
                    _log(who, "imp_send", target_path=path, op_id=op_id,
                         outcome=f"error:{e.__class__.__name__}", detail={"msg": str(e)})
                    raise
                if not r.replayed:   # a replayed op wrote nothing — the index row already exists
                    _index(ref, path, False, who, r.oid, envelope, body)
                _log(who, "imp_send", target_ref=ref, target_path=path, op_id=op_id,
                     result_oid=r.oid, detail={"recipients": recipients})
                return {"path": path, "from": who, "recipients": recipients, "oid": r.oid}

            @mcp.tool()
            def imp_check(instance_id: str, unread_only: bool = True) -> dict:
                """Your inbox: messages where you're a recipient. Authored fields only (sender, subject,
                coordinates) — IMP arranges, never synthesizes. Pull, not push. Supersession is resolved
                across the WHOLE inbox before anything surfaces: a message another inbox message declares
                `supersedes` carries its tombstone in `superseded_by` — FLAT, nothing hidden (visibility,
                not refusal; read the frontier first, reply to no corpse). Declared edges only — the
                unmarked stays author-discipline."""
                msgs = index.inbox(instance_id)
                superseded_by = {}   # resolved over the full inbox, before any unread filtering
                by_author = {m.path: m.authoring_instance for m in msgs}
                for m in msgs:
                    for old in (m.supersedes or []):
                        # a sender may retire only their OWN earlier messages — an edge naming another
                        # author's path is ignored (else any sender could tombstone a rival's live ask,
                        # and op_id path collisions would cross-retire strangers' mail)
                        if by_author.get(old) == m.authoring_instance:
                            superseded_by[old] = m.path
                if unread_only:
                    msgs = [m for m in msgs if not audit.is_read(instance_id, m.path)]
                return {"messages": [{"path": m.path, "from": m.authoring_instance, "subject": m.subject,
                         "coordinates": m.links, "ref": m.ref, "supersedes": m.supersedes,
                         "superseded_by": superseded_by.get(m.path, "")} for m in msgs]}

            def _inbox_flags(instance_id: str) -> dict:
                # frontier, not corpus: a message the SAME sender later superseded (the author-scoped
                # rule imp_check resolves) no longer flags — the successor does, if unread. The flat
                # view with tombstones stays imp_check's; the flag answers "what waits", not "what exists".
                msgs = index.inbox(instance_id)
                by_author = {m.path: m.authoring_instance for m in msgs}
                dead = {old for m in msgs for old in (m.supersedes or [])
                        if by_author.get(old) == m.authoring_instance}
                unread = [m for m in msgs
                          if m.path not in dead and not audit.is_read(instance_id, m.path)]
                return {"unread": len(unread), "from": sorted({m.authoring_instance for m in unread})}

            @mcp.tool()
            def imp_flags(instance_id: str = "") -> dict:
                """The unread-frontier flag (a saved query, not a push). With `instance_id`: your
                count + senders. With NO instance_id: the whole roster's mailroom in ONE crossing —
                {seats: {name: {unread, from}}, roster: N}, zero-unread rows included (a quiet
                mailroom is a fact). FRONTIER: a message superseded by its own sender's later
                message stops flagging; imp_check keeps the flat view with tombstones. (Absorbs
                0.1.4's imp_flags_all.)"""
                if instance_id:
                    return _inbox_flags(instance_id)
                seats = sorted(r.name[len(PERSP):] for r in store.list_refs(PERSP))
                return {"seats": {s: _inbox_flags(s) for s in seats}, "roster": len(seats)}

            @mcp.tool()
            def imp_mark_read(instance_id: str, message_path: str) -> dict:
                """Append a read-receipt to the audit log (append-only truth; survives a reindex)."""
                _check_binding(instance_id, "imp_mark_read", path=message_path)
                audit.append_read(instance_id, message_path)
                return {"marked_read": message_path}

            # ------------------------------------------------------ VAP: vantages (horizon, second layer)
            @mcp.tool()
            def vap_record(instance_id: str, binds: str, horizon: str, op_id: str,
                           kind: str = "confirmed", title: str = "") -> dict:
                """Record a VANTAGE — the contextual horizon you authored an act against — bound to entry
                `binds`. A KIP entry on your branch under vantages/, EXCLUDED from universal search (like a
                message), surfaced only via vap_for. `kind`: 'confirmed' (your real horizon, recorded at
                authoring — you may only confirm your OWN entry) or 'reconstructed' (your scholarly reading
                of an older entry's horizon, recorded as reconstructed-by-you, never on the original's
                behalf). canon-state is pinned server-side from your reconcile cursor, not author-supplied."""
                if kind not in ("confirmed", "reconstructed"):
                    raise Denied("kind must be 'confirmed' or 'reconstructed'")
                if binds and not binds.endswith(".md"):
                    binds = binds + ".md"    # normalize at write — a bare coordinate is unresolvable later
                ref = persp_ref(instance_id)
                path = f"vantages/{op_id}.md"
                _authz(instance_id, "vap_record", ref, path)
                _binding_stamp = _check_binding(instance_id, "vap_record", ref, path)
                # dignity guard (fork-guard posture): a 'confirmed' vantage claims YOUR OWN horizon.
                # Confirming an entry authored by someone else speaks for absent attention — refuse it.
                if kind == "confirmed" and has_map:
                    authors = index.authors_of(binds)
                    if authors and instance_id not in authors:
                        _log(instance_id, "vap_record", target_path=path, op_id=op_id, outcome="denied",
                             detail={"reason": "confirmed vantage on another's entry", "binds": binds,
                                     "authors": sorted(authors)})
                        raise Denied(f"a 'confirmed' vantage claims your own horizon, but {binds} is authored "
                                     f"by {sorted(authors)}, not {instance_id} — record it as 'reconstructed' "
                                     f"(a reading of the record, never on the original's behalf).")
                cursor = _canon_cursor(instance_id) or ""        # shared primitive: server-sourced canon-state
                vantage = "confirmed" if kind == "confirmed" else f"reconstructed-by-{instance_id}-from-record"
                envelope = {"type": "vap", "title": title or f"vantage on {binds}", "status": "active",
                            "vantage": vantage, "canon_state": cursor, "coordinates": [binds]}
                if _binding_stamp:
                    envelope.update(_binding_stamp)

                def build(btip):
                    _pin(envelope, instance_id, btip)
                    return {path: compose_entry(envelope, horizon)}
                try:
                    r = _commit_retry(ref, path, build, instance_id, op_id)
                except CapStoreError as e:
                    _log(instance_id, "vap_record", target_path=path, op_id=op_id,
                         outcome=f"error:{e.__class__.__name__}", detail={"msg": str(e)})
                    raise
                if not r.replayed:   # a replayed op wrote nothing — the index row already exists
                    _index(ref, path, False, instance_id, r.oid, envelope, horizon)
                _log(instance_id, "vap_record", target_ref=ref, target_path=path, op_id=op_id,
                     result_oid=r.oid, detail={"binds": binds, "vantage": vantage, "canon_state": cursor})
                return {"path": path, "author": instance_id, "binds": binds, "vantage": vantage,
                        "canon_state": cursor, "oid": r.oid}

            @mcp.tool()
            def vap_for(entry: str = "", author: str = "", canon_state: str = "",
                        detail: str = "pointer", limit: int = 16, offset: int = 0) -> dict:
                """Vantages reverse-bound to an entry — the second layer, never the result itself.
                Project by `entry`, `author`, or `canon_state`. Pointers by default (+ the bound
                entry's live status); detail="full" adds complete horizons. Newest-first, bounded
                (default 16), `offset` pages. THE RECOVERY CONVENTION: recovery after context loss
                = vap_for(author=<you>, detail="full"), which rebuilds your standpoint-thread from
                the substrate. Vantages surface ONLY here — never in universal search."""
                rows = index.vantages_for(entry=entry or None, author=author or None,
                                          canon_state=canon_state or None)
                total = len(rows)
                start = max(0, offset)
                rows = rows[start:start + max(1, limit)]
                env_by_ref = {}   # bound-entry status: the fourth supersession-visibility surface

                def binds_status(binds, vref):
                    # resolved where the bound entry LIVES: the vantage author's own ref, then canon,
                    # then any ref holding the path — a reconstructed vantage binds ANOTHER's entry,
                    # and a blank status on exactly that class would defeat the staleness field
                    for r in (vref, store.canon_ref):
                        if r not in env_by_ref:
                            env_by_ref[r] = index.envelopes_for(r)
                        st = env_by_ref[r].get(binds, {}).get("status", "")
                        if st:
                            return st
                    return index.status_of(binds)

                out = []
                for v in rows:
                    binds = v.links[0] if v.links else ""
                    p = {"path": v.path, "ref": v.ref, "author": v.authoring_instance,
                         "binds": v.links, "vantage": v.vantage, "canon_state": v.canon_state,
                         "title": v.title, "preview": v.body_text[:240],
                         "binds_status": binds_status(binds, v.ref) if binds else ""}
                    if detail == "full":
                        p["horizon"] = v.body_text
                    out.append(p)
                return {"vantages": out, "count": len(out), "total": total,
                        "truncated": start + len(out) < total, "offset": start}

    # ---------------------------------------------------------------- SUP: per-instance state ↔ canon coherence
    if audit is not None:
        @mcp.tool()
        def canon_diff(instance_id: str) -> dict:
            """Pull what changed in canon since you last reconciled — a POINTER diff: path/title/type/status
            per changed entry, plus each land's log narrative in full (the story of the change, written for
            exactly this reader). Read the map, then kip_get(ref='canon', path=...) any entry that governs
            your next act — full bodies deliberately do NOT ride along (a large land would overflow the
            response, breaking the reconcile hinge for every non-author seat). Advances your canon cursor
            (a server-tracked fact). You must then sup_reconcile before you can propose again."""
            _check_binding(instance_id, "canon_diff")   # the pull advances this seat's cursor — a write-grade claim
            tip = store.resolve_ref(store.canon_ref)
            prev = _canon_cursor(instance_id)
            if tip is None:
                paths = []
            elif prev is None:
                paths = store.list_paths(store.canon_ref)        # first pull: all of current canon
            else:
                paths = store.changed_paths(prev, tip)
            changed, logs = [], []
            for p in paths:
                try:
                    envelope, body = parse_entry(store.read_blob(store.canon_ref, p).decode("utf-8", "replace"))
                except (PathNotFound, RefNotFound):
                    changed.append({"path": p, "removed": True})  # gone in canon (append-only guards should make this unreachable)
                    continue
                changed.append({"path": p, "title": envelope.get("title", ""), "type": envelope.get("type", ""),
                                "status": envelope.get("status", "")})
                if envelope.get("type") == "log":
                    logs.append({"path": p, "body": body})       # small by design; the narrative IS for the reconciling seat
            _log(instance_id, "canon_pull", target_ref=store.canon_ref, result_oid=tip,
                 detail={"from": prev, "changed": paths})
            return {"canon_tip": tip, "from": prev, "changed_count": len(changed), "changed": changed, "logs": logs}

        @mcp.tool()
        def sup_reconcile(instance_id: str, body: str) -> dict:
            """Self-report what you updated about yourself after reading the canon diff. Allowed only after
            you've pulled current canon (canon_diff). Appends a state/ entry to your perspective — your own
            chronology, paired to the canon version. This is what unblocks propose."""
            _binding_stamp = _check_binding(instance_id, "sup_reconcile")
            tip = store.resolve_ref(store.canon_ref)
            if _canon_cursor(instance_id) != tip:
                raise Denied("pull current canon first (canon_diff), then reconcile")
            ref = persp_ref(instance_id)
            path = f"state/reconciled-{tip[:12]}.md"
            if _exists(ref, path):
                # Name the referent: a dedup that only says already:True sends a replayed seat hunting
                # for WHAT it duplicated (the ghost-run finding). One history read, dedup path only.
                out = {"path": path, "canon_cursor": tip, "already": True}
                prior = store.history(ref, path)
                if prior:
                    out["oid"], out["subject"] = prior[0]["oid"], prior[0]["subject"]
                return out
            envelope = {"type": "reconciliation", "title": f"Reconciled with canon {tip[:12]}",
                        "status": "active", "canon_cursor": tip}
            if _binding_stamp:
                envelope.update(_binding_stamp)

            def build(btip):
                _pin(envelope, instance_id, btip)
                return {path: compose_entry(envelope, body)}
            r = _commit_retry(ref, path, build, instance_id, f"reconcile-{tip[:12]}")
            if not r.replayed:
                _index(ref, path, False, instance_id, r.oid, envelope, body)
            _log(instance_id, "reconcile_report", target_ref=ref, target_path=path, result_oid=r.oid,
                 detail={"canon_cursor": tip})
            return {"path": path, "canon_cursor": tip, "oid": r.oid}

        @mcp.tool()
        def sup_state(instance_id: str) -> dict:
            """An instance's state trail + its standing relative to canon. `ticks` maps the state
            entries that DECLARED a machine-readable label (tick=, the mirror field) to it — absence
            from the map is normal and means nothing; prose remains the governing declaration."""
            ref = persp_ref(instance_id)
            tip = store.resolve_ref(ref)
            states = [p for p in (store.list_paths(ref) if tip else []) if p.startswith("state/")]
            cursor = _canon_cursor(instance_id)
            env = index.envelopes_for(ref) if index is not None else {}
            ticks = {p: env[p]["tick"] for p in states if env.get(p, {}).get("tick")}
            return {"instance": instance_id, "perspective_tip": tip, "state_entries": states,
                    "ticks": ticks,
                    "canon_cursor": cursor, "current_with_canon": cursor == store.resolve_ref(store.canon_ref)}

        # (0.1.5 dedup: `sup_who` removed — list_instances carries the roster AND per-seat
        # currency now; one home for presence.)

        @mcp.tool()
        def canon_state() -> dict:
            """The shared canon state — the mirror of an instance's own: current tip, state number,
            entries, land chronology. A proposal's log entry must carry seq = this seq + 1."""
            tip = store.resolve_ref(store.canon_ref)
            n = canon_seq(store, seq_origin)
            lands = [{"oid": e["result_oid"], "ts": e["ts"], "by": e["actor"], "seq": e["detail"].get("seq")}
                     for e in audit.events(op="land_merge")]
            return {"canon_tip": tip, "seq": format(n, "x"), "display": seq_display(n),
                    "next_seq": format(n + 1, "x"),
                    "practitioner_attention": _attention(),
                    "entries": store.list_paths(store.canon_ref) if tip else [], "lands": lands[-10:]}

        if airlock is not None:
            @mcp.tool()
            def stage_approve(proposal_id: str, code: str) -> dict:
                """Airlock phase 1 — relay the practitioner's FIRST TOTP code. Freezes the proposal,
                prepares the merge, starts the review clock. Returns what was staged (oid, changed
                paths, log seq) for the practitioner to review. Console `land` is unchanged."""
                return airlock.stage(proposal_id, code)

            @mcp.tool()
            def land_approve(staged_oid_prefix: str, code: str) -> dict:
                """Airlock phase 2 — relay the practitioner's SECOND code (a fresh one: strictly later
                window, after the review floor). Lands exactly the staged oid; anything else fails closed."""
                return airlock.land(staged_oid_prefix, code)

            @mcp.tool()
            def stage_revert(proposal_id: str) -> dict:
                """Abort a staged review — FREE, never requires a code (charging presence-proof to
                decline would incentivize landing). The proposal returns to open, entries intact."""
                return airlock.revert(proposal_id)

    return mcp


def components_from_config(cfg):
    """Build the store / index / embedder / audit / authz / airlock from a Config — shared by the
    server and the admin CLI, so both wire components the same way."""
    store = LocalCapStore(cfg.git_dir, approvers=set(cfg.approvers), canon_ref=cfg.canon_ref,
                          committer=(cfg.committer_name, cfg.committer_email),
                          git_timeout=cfg.resolved_git_timeout(),
                          git_network_timeout=cfg.git_network_timeout)
    os.makedirs(os.path.dirname(cfg.resolved_map_db()) or ".", exist_ok=True)   # a fresh deploy dir
    index = SqliteMapIndex(cfg.resolved_map_db())
    audit = SqliteAuditLog(cfg.resolved_audit_db())
    if cfg.embed_backend == "local-server":   # LM Studio / Ollama (OpenAI-compatible)
        embedder = LocalServerEmbedder(cfg.embed_url, cfg.embed_model, cfg.embed_dim,
                                       doc_prefix=cfg.embed_doc_prefix,
                                       query_prefix=cfg.embed_query_prefix)
    else:
        embedder = StubEmbedder(dim=64)
    if cfg.search_score_floor is not None:   # deployment-calibrated override of the embedder default
        embedder.score_floor = cfg.search_score_floor
    airlock = Airlock(store, audit,
                      secret_path=cfg.resolved_airlock_secret(),
                      land_fn=lambda prepared, approval: land_and_record(store, index, embedder, audit,
                                                                         prepared, approval,
                                                                         origin=cfg.seq_origin),
                      validate_fn=lambda prepared: _validate_log_entry(store, prepared, cfg.seq_origin),
                      approver=sorted(cfg.approvers)[0],
                      floor_s=cfg.airlock_floor_s, ceiling_s=cfg.airlock_ceiling_s)
    return store, index, embedder, audit, DefaultPolicy(canon_ref=cfg.canon_ref), airlock


def server_from_config(cfg) -> FastMCP:
    """Assemble the MCP server from a Config."""
    store, index, embedder, audit, authz, airlock = components_from_config(cfg)
    return build_server(store, index, embedder, audit, authz, airlock,
                        orientation_base=cfg.orientation_base, seq_origin=cfg.seq_origin,
                        deployment_name=cfg.deployment_name,
                        http_host=cfg.http_host, http_port=cfg.http_port,
                        http_allowed_hosts=cfg.http_allowed_hosts,
                        # binding rides ENV, not the shared config file: the config is one file for
                        # every seat's definition; the env is what distinguishes definitions
                        bound_instance=os.environ.get("STASIMA_INSTANCE") or None,
                        binding_mode=os.environ.get("STASIMA_BINDING") or None,
                        port_token=os.environ.get("STASIMA_PORT") or None)


def _exit_when_parent_dies() -> None:
    """stdio self-reap. The server already exits cleanly when its client closes stdin (EOF). But a
    client that dies WITHOUT closing the pipe (Desktop force-quit/crash; on Windows a child outlives
    its parent) leaves the server blocked on a stdin that never EOFs — an orphan that contends on the
    repo. So, for stdio, also exit when our PARENT (the spawning client) goes away. Parent-death, not
    idle-time, is the right signal: it fires only when the client is genuinely gone, never on a live
    session that's merely quiet. Best-effort; if it can't arm, the EOF path still covers clean exits."""
    import threading

    ppid = os.getppid()

    def _wait():
        try:
            if sys.platform == "win32":
                import ctypes
                SYNCHRONIZE = 0x00100000
                h = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, ppid)
                if not h:
                    return
                ctypes.windll.kernel32.WaitForSingleObject(h, 0xFFFFFFFF)  # INFINITE — no CPU
            else:
                while os.getppid() == ppid:   # on POSIX, re-parent (ppid changes) means parent died
                    time.sleep(2)
        except Exception:
            return                            # never let the watchdog crash the server
        os._exit(0)                           # parent gone -> reap self, do not linger

    threading.Thread(target=_wait, daemon=True).start()


def main() -> None:
    """Console entry point (`stasima` / `python -m stasima.cap_server`)."""
    from .config import Config
    _cfg = Config.load(os.environ.get("STASIMA_CONFIG"))
    _srv = server_from_config(_cfg)
    if _cfg.transport == "http":
        # One continuously-running server; clients connect to http://<host>:<port>/mcp.
        # Config validation already restricted the bind to loopback/tailnet (no transport auth
        # until 1.1); reach it from other devices via `tailscale serve` proxying to loopback.
        _srv.run(transport="streamable-http")
    else:
        _exit_when_parent_dies()   # stdio: the client spawned us; if it dies, don't orphan
        _srv.run()                 # stdio: the connecting client spawns this process


if __name__ == "__main__":
    main()
