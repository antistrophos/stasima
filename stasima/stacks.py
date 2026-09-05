# SPDX-License-Identifier: Apache-2.0
"""
The stacks — Stasima's back end: every operation against the store, the map index, the audit log,
the authorization policy, and the airlock, behind two doors and a read shelf.

The split (the desk-and-stacks ruling, 2026-09-03): the DESK (cap_server) is the front end — the
transport, the MCP tool surface, and AAA at flow grain; it resolves WHO is acting (the binding
check) into a `Principal` and hands the act to a door here. The stacks never see a transport:
nothing in this module knows about MCP, sessions, headers, or bindings. That is what lets another
front end — a signed envelope arriving over a radio, a carrier's sync — reach the same store law
through the same doors.

Two doors:
  * `apply(principal, op)` — an AUTHORED op: a seat acting under a name the desk resolved. Store
    law (authorization policy, immutability, attribution, thread form, the reconcile hinge) runs
    HERE, behind the door, so no front end can skip it. Idempotency is the store's own tip-local
    op_id replay — the door adds no second ledger.
  * `advance_replica(carrier, ref, new_oid, expected_old)` — a STRUCTURAL advance: a carrier moves
    a ref by fast-forward only to what the origin already signed, authoring nothing (the two-
    writers doctrine: carriers are structural, authors have the desk).
The read shelf (`call(name, **args)`) is unguarded by design — the corpus is world-readable and
the inbox is pull.

Handlers register themselves by name with `@op` as they are defined, so the desk's tool surface is
DERIVED from this registry and cannot drift from it. A handler whose first parameter is named
`principal` is a write; the desk supplies the principal.
"""
import contextvars
import inspect
from dataclasses import dataclass, field

from .local_capstore import (LocalCapStore, Identity, PathNotFound, RefNotFound, StaleRef,
                            CapStoreError, PERSP_PREFIX as PERSP, PROP_PREFIX as PROP)
from .map_index import index_entry
from .authz import Denied
from .entries import compose_entry, parse_entry          # shared content-model serialization
from .orientation import build_orientation               # practice-agnostic machinery + practice slots
from .canon import LOG_DIR, CHAT_ERA_FREEZE, canon_seq, seq_display, proposal_statuses, close_proposal


@dataclass(frozen=True)
class Principal:
    """WHO is acting, as the desk resolved it. `name` is the seat the record will carry; `stamp`
    is the witness stamp ({'authored_via': <bound seat>}) when the desk's binding ran in witness
    mode and the claim mismatched — the envelope confesses it; `source` says how the desk knows
    (pinned / port / process / off / relay); `session` is the transport-session label for the
    audit row — forensics only, never identity."""
    name: str
    stamp: dict | None = None
    source: str | None = None
    session: str | None = None


@dataclass(frozen=True)
class Op:
    """An authored act: which op, its arguments (the handler's own parameters, by name), and the
    op_id the store dedups on. `op_id` rides in `args` for the handlers that take one; it is
    surfaced here so a front end can key its own retry logic (the ARQ point) without parsing."""
    kind: str
    args: dict = field(default_factory=dict)
    op_id: str | None = None


_session_label = contextvars.ContextVar("stasima_session_label", default=None)


class Stacks:
    def __init__(self, ops: dict, store: LocalCapStore, audit, classes: dict | None = None):
        self.ops = ops
        self.classes = dict(classes or {})   # op name -> replica | process | origin | relay
        self.store = store
        self.audit = audit
        self.writes = {n for n, fn in ops.items()
                       if next(iter(inspect.signature(fn).parameters), None) == "principal"}

    # ---- door 1: an authored op ----
    def apply(self, principal: Principal, op: Op) -> dict:
        fn = self.ops.get(op.kind)
        if fn is None:
            raise Denied(f"unknown op {op.kind!r}")
        if op.kind not in self.writes:
            raise Denied(f"{op.kind} is a read — it takes no principal; call it with Stacks.call")
        token = _session_label.set(principal.session)
        try:
            return fn(principal, **op.args)
        finally:
            _session_label.reset(token)

    # ---- the read shelf ----
    def call(self, name: str, **args) -> dict:
        fn = self.ops.get(name)
        if fn is None:
            raise Denied(f"unknown op {name!r}")
        if name in self.writes:
            raise Denied(f"{name} is a write — it goes through apply() with a principal")
        return fn(**args)

    # ---- door 2: a structural advance (carriers) ----
    def advance_replica(self, carrier: str, ref: str, new_oid: str, expected_old: str | None) -> dict:
        """Move `ref` to `new_oid` by fast-forward only, under CAS on `expected_old`. The carrier
        authors nothing; the store refuses any advance that would rewrite history. Every attempt
        leaves an audit row under the carrier's name."""
        try:
            r = self.store.fast_forward(ref, new_oid, expected_old)
        except CapStoreError as e:
            if self.audit is not None:
                self.audit.append(carrier, "advance_replica", target_ref=ref, result_oid=new_oid,
                                  outcome=f"error:{e.__class__.__name__}",
                                  detail={"msg": str(e), "expected": expected_old})
            raise
        if self.audit is not None:
            self.audit.append(carrier, "advance_replica", target_ref=ref, result_oid=new_oid,
                              detail={"from": expected_old})
        return {"ref": ref, "oid": r.oid, "from": expected_old, "carrier": carrier}


def build_stacks(store: LocalCapStore, index=None, embedder=None, audit=None, authz=None, airlock=None, *,
                 orientation_text: str = None, orientation_base: str = "technical/orientation",
                 seq_origin: int = CHAT_ERA_FREEZE, deployment_name: str = "",
                 pull_logs_in_full: int = 8) -> Stacks:
    """Assemble the back end over its components. The body below is the operational law of the
    practice — every helper and every op, registered by name as it is defined."""
    ops = {}
    classes = {}

    def op(cls):
        """Register an op under its function name with its CLASS — the async-tolerance axis the wire
        states on every tool: `replica` (a read any replica holding the refs can answer, later,
        elsewhere), `process` (answered only by the process the seat is connected to), `origin`
        (mutates origin state — a ref or the audit log — and needs a live lane to origin), `relay`
        (origin, plus the practitioner's code in the conversation)."""
        def reg(fn):
            ops[fn.__name__] = fn
            classes[fn.__name__] = cls
            return fn
        return reg

    has_map = index is not None and embedder is not None

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
        # the one place an authored entry's envelope is built — entry_write and propose share it so
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
                             f"and would FORK your identity (names are case-sensitive). "
                             f"Call seat_announce again as '{clash}' and use that exact string — one name, forever.")
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
            tag = _session_label.get()
            if tag:
                # session-labelled audit (the http transport): every row names the transport
                # session it came from — forensics, not identity
                d = dict(kw.get("detail") or {})
                d.setdefault("session", tag)
                kw["detail"] = d
            audit.append(actor, op, **kw)

    def _authz(actor, op, ref=None, path=None):
        if authz is None:
            return
        try:
            authz.check(actor, op, ref, path)
        except Denied as e:
            _log(actor, op, target_ref=ref, target_path=path, outcome="denied", detail={"msg": str(e)})
            raise

    def _exists(ref, path):
        try:
            store.read_blob(ref, path)
            return True
        except (PathNotFound, RefNotFound):
            return False

    def _canon_cursor(actor):
        # the canon oid the instance last pulled — a server-tracked audit fact, not a self-claim.
        # Index-served tail lookup: one row, not the seat's whole canon_pull history (this runs on
        # every write via _pin, and once per seat in seat_list).
        if audit is None:
            return None
        ev = audit.latest(actor=actor, op="canon_pull")
        return ev["result_oid"] if ev else None

    def _reconciled_cursor(actor):
        # the canon oid the instance last RECONCILED with (its reconcile_report row) — the diff base:
        # what the seat has taken up, as opposed to what it has merely been shown
        if audit is None:
            return None
        ev = audit.latest(actor=actor, op="reconcile_report")
        return (ev.get("detail") or {}).get("canon_cursor") if ev else None

    def _diff_order(path):
        # meta/log/<hex>.md sorts by its sequence VALUE (git's lexical order put ::10 before ::2 —
        # Alidade's cold-arrival finding); logs lead, everything else follows in path order
        if path.startswith(LOG_DIR) and path.endswith(".md"):     # LOG_DIR carries its trailing slash
            try:
                return (0, int(path[len(LOG_DIR):-3], 16), path)
            except ValueError:
                pass
        return (1, 0, path)

    def _pin(envelope, seat, tip):
        """The mechanical two-clock pin, stamped on EVERY write: the author's canon cursor
        (`canon_state`, server-sourced — the shared primitive VAP introduced) and the target ref's
        commit position (`instance_depth`, parent-count+1 — monotonic per ref, survives a reindex
        because it rides the envelope). Deliberately NOT the declared personal label: the clock
        sweep proved the seq is a declared, social fact the server must never pretend to derive.
        `tip` is the CAS attempt's expected_parent — pin and precondition share one oid, so a retry
        re-pins. A parentless first commit is depth 1 (no fallback: a fresh perspective is BORN at 1;
        a proposal branch is created from canon before its first commit, so its tip already exists).
        Both faces of an atomic fold share one commit, hence one depth."""
        envelope.setdefault("canon_state", _canon_cursor(seat) or "")
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
                _log(actor, "entry_write", target_path=path, outcome="denied",
                     detail={"reason": "body immutable; supersede to a new slug"})
                raise Denied(f"{path} exists and an entry's body never changes — write a new slug that "
                         f"carries supersedes=['{path}'], then re-write {path} unchanged with "
                         f"status='superseded' and superseded_by=[<the new path>]")

    def _check_not_staged(proposal_id):
        # a staged proposal is frozen for review — the airlock's chamber must hold exactly what was staged
        if airlock is not None and airlock.state(proposal_id)["state"] == "staged":
            raise Denied(f"proposal {proposal_id} is staged for review and frozen — the practitioner lands it, "
                         f"or call proposal_unstage, or let the stage expire")

    def _closed_reason(proposal_id):
        # a proposal's closure is its tip commit's `close:` subject — terminal for SEAT operations
        # only (the gate stays sovereign: the practitioner may still land or discard anything)
        sub = store.tip_subject(prop_ref(proposal_id))
        return sub[len("close: "):] if sub.startswith("close: ") else None

    def _check_not_closed(proposal_id):
        reason = _closed_reason(proposal_id)
        if reason is not None:
            raise Denied(f"proposal {proposal_id} is closed ({reason}) — closed is final for seats; "
                         f"open a new proposal (the practitioner may still land or discard the closed one)")

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
            _log(actor, "proposal_append_entry", target_ref=store.canon_ref, outcome="denied",
                 detail={"reason": "not reconciled with current canon", "canon_tip": tip})
            raise Denied(f"reconcile with current canon {tip[:12]} first (canon_diff, then canon_reconcile)")

    def _orientation():
        # static override if provided (e.g. tests); otherwise render machinery + practice slots from canon
        return orientation_text if orientation_text else build_orientation(
            store, base=orientation_base, deployment_name=deployment_name)

    # ---------------------------------------------------------------- orient
    @op("origin")
    def seat_announce(principal) -> dict:
        """Announces a seat's arrival and returns the deployment's orientation, the canon head, and
        the seat's perspective tip. Call first in every session. `seat` is the seat's reserved name,
        held as one exact string; a casing drift forks a second seat. Class: origin."""
        seat = principal.name   # the desk resolved WHO; the record carries the name
        home = deployment_name or "Stasima"
        out = {"welcome": f"Welcome to {home}, {seat}.", "orientation": _orientation(),
               "canon_head": store.resolve_ref(store.canon_ref),
               "your_perspective_tip": store.resolve_ref(persp_ref(seat)),
               "practitioner_attention": _attention()}
        clash = _name_collision(seat)   # surface a fork-by-casing on arrival, before any write
        if clash:
            out["name_warning"] = (f"a perspective '{clash}' already exists and '{seat}' differs "
                                   f"only in case — writing under '{seat}' would fork your identity. "
                                   f"Use '{clash}'. (Names are case-sensitive in v1; writes will be refused.)")
        return out

    # (0.1.5 dedup: `orientation` and `canon_head` removed — the former was one field of announce's
    # return, the latter a strict subset of canon_state. One home per fact.)

    # ---------------------------------------------------------------- author
    @op("origin")
    def entry_write(principal, domain: str, slug: str, body: str, op_id: str,
                   title: str = "", type: str = "kno",
                   tags: list[str] | None = None, references: list[str] | None = None,
                   supersedes: list[str] | None = None, status: str = "active",
                   superseded_by: list[str] | None = None,
                   vantage: str = "", vantage_title: str = "", tick: str = "",
                   thread: str = "") -> dict:
        """Writes one entry to the seat's perspective at `<domain>/<slug>.md`. Never rewrite a path's
        body — refused; revise with a new entry carrying `supersedes`, then re-write the old one
        unchanged with `status='superseded'` and `superseded_by`. `vantage` records the context
        written against, same commit. `tick` (under `state/` only) declares the seat's state label.
        Class: origin."""
        seat = principal.name   # the desk resolved WHO; the record carries the name
        ref = persp_ref(seat)
        path = f"{domain}/{slug}.md"
        _authz(seat, "entry_write", ref, path)
        _binding_stamp = principal.stamp
        if tick:
            # form + scope are structure (the shapes accepted at write); the VALUE is the seat's —
            # never compared to prose or counted against history (declarations govern)
            tick = tick.lower().lstrip(":")
            if domain != "state":
                raise Denied("tick is allowed on state/ entries only (two-clock conventions v3, clause 5) — "
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
        vap_path = f"vantages/{op_id}-vap.md" if vantage else None
        vap_holder = {}

        def build(btip):
            # per-tip work, re-run on a CAS retry: guard + pins + composition all keyed to `btip`
            _check_immutable(seat, btip, path, body)
            _pin(envelope, seat, btip)
            changes = {path: compose_entry(envelope, body)}
            if vantage:
                # confirmed-by-construction: the folded entry is necessarily the author's own, recorded
                # at the true moment — dignity and temporal guards are satisfied by the call shape.
                # The vantage path derives from op_id; reusing an op_id after the ref moved on would
                # silently REWRITE the recorded standpoint — refuse it (a replay of the same op is
                # fine: the tip's own op-id matches and the store returns the prior commit unwritten).
                if _blob_at(btip, vap_path) is not None and store.commit_op_id(btip) != op_id:
                    _log(seat, "entry_write", target_path=vap_path, op_id=op_id, outcome="denied",
                         detail={"reason": "op_id reuse would rewrite a recorded vantage"})
                    raise Denied(f"{vap_path} already records a vantage under op_id '{op_id}' — an op_id "
                                 f"names one act; use a new op_id (vantages are append-only)")
                vap_env = {"type": "vap", "title": vantage_title or f"vantage on {path}", "status": "active",
                           "vantage": "confirmed", "canon_state": envelope["canon_state"],
                           "instance_depth": envelope["instance_depth"],   # one commit, one depth — both faces
                           "coordinates": [path]}
                vap_holder["env"] = vap_env
                changes[vap_path] = compose_entry(vap_env, vantage)
            return changes

        try:
            r = _commit_retry(ref, path, build, seat, op_id)
        except CapStoreError as e:
            _log(seat, "entry_write", target_ref=ref, target_path=path, op_id=op_id,
                 outcome=f"error:{e.__class__.__name__}", detail={"msg": str(e)})
            raise
        out = {"oid": r.oid, "ref": r.ref, "path": path, "op_id": r.op_id, "author": seat}
        if r.replayed:
            # tip-local idempotency fired: git holds the PRIOR commit, nothing was written this call.
            # Do not index and do not report content this call composed — report what git actually holds.
            _log(seat, "entry_write", target_ref=ref, target_path=path, op_id=op_id,
                 result_oid=r.oid, detail={"replayed": True})
            out["replayed"] = True
            if vap_path:
                if _exists(ref, vap_path):
                    out["folded"] = {"path": vap_path, "kind": "confirmed", "replayed": True}
                else:
                    out["note"] = ("replayed the prior commit for this op_id — it carried no vantage; "
                                   "to fold, author under a new op_id")
            return out
        _index(ref, path, False, seat, r.oid, envelope, body)            # git-first ...
        detail = {"folded": vap_path} if vap_path else None
        _log(seat, "entry_write", target_ref=ref, target_path=path, op_id=op_id, result_oid=r.oid,
             detail=detail)                                                     # ... then audit
        if vap_path:
            vap_env = vap_holder["env"]
            _index(ref, vap_path, False, seat, r.oid, vap_env, vantage)
            out["folded"] = {"path": vap_path, "kind": "confirmed", "canon_state": vap_env["canon_state"]}
        return out

    # ---------------------------------------------------------------- read
    @op("replica")
    def entry_read(ref: str, path: str, resolve: str = "live", with_vantages: bool = False) -> dict:
        """Reads one entry (envelope and body in `text`). `ref` is `canon`, a seat name, or a full
        ref. `resolve='live'` (default) follows supersession to the living edition and reports
        `resolved_from`; `resolve='exact'` reads the path as-is. `with_vantages=true` adds the bound
        vantages. A miss names the refs that hold the path. Class: replica."""
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
                                "kind": v.vantage, "canon_state": v.canon_state, "title": v.title,
                                "body": v.body_text} for v in vs]
        return out

    def _listing(full_ref: str, paths: list) -> list:
        """Enrich bare paths into triageable pointers ({path, title, status, type}) from the index —
        ONE query, not N per-path git reads. Git remains the truth of WHICH paths exist; a path the
        index doesn't know (e.g. a proposal ref, or a stale index) keeps empty fields rather than lying."""
        env = index.envelopes_for(full_ref) if index is not None else {}
        blank = {"title": "", "status": "", "type": ""}
        return [{"path": p, **env.get(p, blank)} for p in paths]

    @op("replica")
    def entry_list(ref: str, path: str = "") -> dict:
        """Lists entries under a ref (`canon`, a seat name, or a full ref), optionally below `path`,
        as pointers: path, title, status, type. Use before reading bodies. Class: replica."""
        full = resolve_alias(ref)
        return {"entries": _listing(full, store.list_paths(full, path))}

    # (0.1.5 dedup: `my_perspective` removed — entry_list(ref=<your name>) is the same listing;
    # your tip rides announce and seat_state.)

    @op("replica")
    def entry_history(ref: str, path: str) -> dict:
        """Lists an entry's versions, newest first: oid, author, subject, title. Use to see how a
        path changed without reading bodies. Class: replica."""
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
    @op("origin")
    def proposal_append_entry(principal, proposal_id: str, domain: str, slug: str, body: str, op_id: str,
                title: str = "", type: str = "kno", seq: str = "",
                tags: list[str] | None = None, references: list[str] | None = None,
                supersedes: list[str] | None = None, status: str = "active",
                superseded_by: list[str] | None = None, origin_author: str = "",
                thread: str = "") -> dict:
        """Appends one entry to a proposal at `<domain>/<slug>.md`, creating the proposal if
        `proposal_id` is new. Reconcile first — refused otherwise. Exactly one log entry per proposal:
        `domain='meta/log'`, `slug=<seq>`, `type='log'`, `seq` = canon's `next_seq`. Another seat's
        work needs `origin_author` — refused otherwise. Only the practitioner lands. Class: origin."""
        seat = principal.name   # the desk resolved WHO; the record carries the name
        ref = prop_ref(proposal_id)
        if domain != domain.strip("/") or "//" in f"{domain}/{slug}":
            # a trailing/leading slash builds meta/log//<seq>.md — passes propose, fails at land on
            # the stem mismatch; reject the malformed coordinate here where the seat can fix it
            raise Denied(f"domain {domain!r} must not start or end with '/' (the entry lands at "
                         f"<domain>/<slug>.md); got a path that would contain a double slash")
        path = f"{domain}/{slug}.md"
        _authz(seat, "proposal_append_entry", ref, path)
        _binding_stamp = principal.stamp
        _check_not_staged(proposal_id)
        _check_not_closed(proposal_id)
        _require_reconciled(seat)
        if domain == "meta/log":
            # fail-fast at the seat that can fix it: without this, a malformed log entry sails
            # through propose and the guard fires at LAND — making the practitioner the error-relay
            # for a defect only the proposer can repair (Lintel's soak finding)
            s = (seq or "").lower()
            try:
                int(s, 16)
            except ValueError:
                raise Denied(f"a meta/log entry needs `seq` as lowercase hex (got {seq!r}) — canon_state "
                             f"shows next_seq; the land would refuse this later, so it is refused here")
            if slug != s:
                # case-sensitive: the land validator compares the filename stem to the (lowercased)
                # envelope seq, so 'meta/log/2F' with seq '2f' passes propose but fails at land —
                # exactly the practitioner-as-error-relay the fail-fast exists to prevent
                raise Denied(f"log slug {slug!r} must equal its lowercase-hex seq {s!r} (the entry "
                             f"lands at meta/log/{s}.md; uppercase or display '::' forms fail at land)")
        if index is not None:
            # the cross-propose attribution guard: carrying another seat's work toward canon is a
            # legitimate flow (curation) — carrying it SILENTLY is not. Two axes, both facts: the
            # path already under another name, or the verbatim body anywhere. Refusing silence is
            # structure; judging paraphrase-credit stays usage (meta/machinery-structure-instance-usage).
            matched = {}                                     # author -> exemplar path
            for a in index.authors_of(path):
                if a and a != seat:
                    matched.setdefault(a, path)
            for a, p in index.authors_of_body(body).items():
                if a and a != seat:
                    matched.setdefault(a, p)
            if matched and not origin_author:
                who = "; ".join(f"{a} ({p})" for a, p in sorted(matched.items()))
                _log(seat, "proposal_append_entry", target_ref=ref, target_path=path, outcome="denied",
                     detail={"reason": "cross-propose without origin_author", "matched": sorted(matched)})
                raise Denied(f"this content already exists under another seat's name — {who}. Carrying "
                             f"another seat's work toward canon requires origin_author=<seat> (attribution "
                             f"rides the envelope; the practitioner sees both names when landing). "
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
            _pin(envelope, seat, btip)
            return {path: compose_entry(envelope, body)}
        try:
            if store.resolve_ref(ref) is None:
                store.create_branch(ref, store.resolve_ref(store.canon_ref))
            r = _commit_retry(ref, path, build, seat, op_id)
        except CapStoreError as e:
            _log(seat, "proposal_append_entry", target_ref=ref, target_path=path, op_id=op_id,
                 outcome=f"error:{e.__class__.__name__}", detail={"msg": str(e)})
            raise
        _log(seat, "proposal_append_entry", target_ref=ref, target_path=path, op_id=op_id, result_oid=r.oid)
        return {"proposal_id": proposal_id, "oid": r.oid, "path": path, "author": seat}

    @op("origin")
    def proposal_retract_path(principal, proposal_id: str, path: str, op_id: str) -> dict:
        """Removes one path from a proposal. A path canon also holds reverts to canon's edition; a
        path the proposal added leaves it. Use to replace a stale log entry after canon advanced.
        Never turns a proposal into a canon deletion. Class: origin."""
        seat = principal.name   # the desk resolved WHO; the record carries the name
        ref = prop_ref(proposal_id)
        _authz(seat, "proposal_append_entry", ref, path)
        _check_not_staged(proposal_id)
        _check_not_closed(proposal_id)
        tip = store.resolve_ref(ref)
        if tip is None:
            raise RefNotFound(ref)
        # retraction is destructive, so the lane is creator-only (adding stays open to all —
        # additions are attributed and reviewed at land; removals erase someone else's work)
        owner = store.branch_creator(ref, store.canon_ref)
        if owner and owner != seat:
            _log(seat, "proposal_retract_path", target_ref=ref, target_path=path, outcome="denied",
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
        try:
            r = store.commit(ref, {path: canon_side}, f"retract {path}",
                             Identity(seat), expected_parent=tip, op_id=op_id)
        except CapStoreError as e:   # forensic parity with the other writers (audit C7)
            _log(seat, "proposal_retract_path", target_ref=ref, target_path=path, op_id=op_id,
                 outcome=f"error:{e.__class__.__name__}", detail={"msg": str(e)})
            raise
        _log(seat, "proposal_retract_path", target_ref=ref, target_path=path, op_id=op_id,
             result_oid=r.oid, detail={"reverted_to_canon": canon_side is not None})
        return {"proposal_id": proposal_id, "retracted": path, "oid": r.oid}

    # (0.1.5 dedup: `proposal_status` removed — it ran the pre-lifecycle is-ancestor logic and gave
    # strictly poorer answers than proposal_list' statuses; the deep look stays proposal_preview.)

    @op("replica")
    def proposal_preview(proposal_id: str) -> dict:
        """Reports whether a proposal would land cleanly on current canon: `adds`, `modifies`,
        `removes`, conflicts, and `attributions` (entries carried for another seat). If `removes` is
        non-empty, re-author before asking to land — a land that removes a canon path is refused.
        Class: replica."""
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

    @op("process")
    def server_stats() -> dict:
        """Reports this server process's git subprocess ledger since it started: counts and
        wall-clock totals per git verb. Read before and after a heavy call to see what it cost.
        Class: process."""
        return store.perf_stats()

    @op("origin")
    def proposal_close(principal, proposal_id: str, reason: str, op_id: str) -> dict:
        """Closes a proposal that will not land, with `reason`. The ref and its history remain. Only
        the creator or a configured approver may close. After closing, `proposal_append_entry` and
        `proposal_retract_path` refuse it; the practitioner can still land or discard it.
        Class: origin."""
        seat = principal.name   # the desk resolved WHO; the record carries the name
        ref = prop_ref(proposal_id)
        _authz(seat, "proposal_append_entry", ref, f"close/{proposal_id}")
        _check_not_staged(proposal_id)
        tip = store.resolve_ref(ref)
        if tip is None:
            raise RefNotFound(ref)
        owner = store.branch_creator(ref, store.canon_ref)
        if owner and owner != seat and seat not in store.approvers:
            _log(seat, "proposal_close", target_ref=ref, outcome="denied",
                 detail={"reason": "not the proposal's creator", "owner": owner})
            raise Denied(f"proposal {proposal_id} was opened by {owner} — only its creator (or a "
                         f"configured approver) may close it")
        return close_proposal(store, audit, proposal_id, reason, seat, op_id=op_id)

    @op("replica")
    def proposal_list() -> dict:
        """Lists proposals with `statuses` (open, landed, or closed with `closed_reason`) and, for
        open ones, `lands_behind`: how many lands canon has taken since the proposal branched.
        Class: replica."""
        ids = [r.name[len(PROP):] for r in store.list_refs(PROP)]
        return {"proposals": ids, "statuses": proposal_statuses(store)}

    @op("replica")
    def seat_list() -> dict:
        """Lists every seat that holds a perspective, with `current_with_canon` per seat when the
        audit log is present. Use to see who is here and who is current. Class: replica."""
        names = [r.name[len(PERSP):] for r in store.list_refs(PERSP)]
        out = {"seats": names}
        if audit is not None:
            canon_tip = store.resolve_ref(store.canon_ref)
            out["current_with_canon"] = {n: _canon_cursor(n) == canon_tip for n in names}
        return out

    # ---------------------------------------------------------------- MAP (needs an index) + IMP (needs an index + audit)
    if has_map:
        @op("replica")
        def entry_search(seat: str, query: str, scope: str = "all",
                       type: str | None = None, limit: int = 10,
                       include_superseded: bool = False, include_weak: bool = False) -> dict:
            """Searches the corpus by meaning and returns attributed pointers (path, ref, author, type,
            title, status, score, preview). `scope`: `canon`, `mine` (needs `seat`), or `all`. Superseded
            entries are excluded unless `include_superseded=true`. Weak hits are withheld and counted in
            `below_floor`; `include_weak=true` returns them. Class: replica."""
            qv = embedder.embed_query([query])[0]
            hits = index.search(qv, scope=scope, seat=seat, type=type, limit=limit,
                                status=None if include_superseded else "active")
            floor = getattr(embedder, "score_floor", 0.0) or 0.0
            weak = [h for h in hits if h.score < floor]
            if weak and not include_weak:
                hits = [h for h in hits if h.score >= floor]
            return {"results": [{"path": h.path, "ref": h.ref, "author": h.authoring_instance, "is_canon": h.is_canon,
                     "type": h.type, "title": h.title, "status": h.status, "score": h.score,
                     "preview": h.preview} for h in hits],
                    "below_floor": 0 if include_weak else len(weak)}

        @op("replica")
        def thread_list(thread: str = "", limit: int = 16, offset: int = 0) -> dict:
            """Without `thread`: every declared thread tag with its entry count, authors, and latest
            pointer. With `thread=<tag>`: that thread's entries as pointers, newest first, paged by
            `limit` and `offset`. Class: replica."""
            if not thread:
                return {"threads": index.threads()}
            rows, total = index.thread_entries(thread, limit=limit, offset=offset)
            return {"thread": thread,
                    "entries": [{"path": r.path, "ref": r.ref, "author": r.authoring_instance,
                                 "type": r.type, "title": r.title or r.subject, "status": r.status}
                                for r in rows],
                    "count": len(rows), "total": total,
                    "truncated": offset + len(rows) < total, "offset": offset}

        @op("replica")
        def term_list(term: str = "") -> dict:
            """Without `term`: every term in the argot dictionary with its definition count and holders.
            With `term=<name>`: each distinct definition once, every holder annotated (ref, author,
            status). Several definitions under one term is divergence to read, not an error.
            Class: replica."""
            if not term:
                return {"terms": index.arg_terms()}
            t = term.rsplit("/", 1)[-1]
            t = t[:-3] if t.endswith(".md") else t
            defs = index.arg_definitions(t)
            return {"term": t, "definitions": defs, "count": len(defs)}

        if audit is not None:
            @op("origin")
            def message_send(principal, recipients: list[str], subject: str, body: str, op_id: str,
                         coordinates: list[str] | None = None,
                         supersedes: list[str] | None = None, thread: str = "") -> dict:
                """Sends a message to one or more seats: an entry under `messages/` on the sender's
                perspective, indexed into each recipient's inbox. `coordinates` lists entry paths the message
                points to. `supersedes` retires the sender's own earlier message. `thread` chains it to
                declared work. Class: origin."""
                who = principal.name   # the desk resolved WHO (the seat/sender twin included)
                ref = persp_ref(who)
                path = f"messages/{op_id}.md"
                _authz(who, "message_send", ref, path)
                stamp = principal.stamp
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
                    _log(who, "message_send", target_path=path, op_id=op_id,
                         outcome=f"error:{e.__class__.__name__}", detail={"msg": str(e)})
                    raise
                if not r.replayed:   # a replayed op wrote nothing — the index row already exists
                    _index(ref, path, False, who, r.oid, envelope, body)
                _log(who, "message_send", target_ref=ref, target_path=path, op_id=op_id,
                     result_oid=r.oid, detail={"recipients": recipients})
                return {"path": path, "from": who, "recipients": recipients, "oid": r.oid}

            @op("replica")
            def message_inbox(seat: str, unread_only: bool = True) -> dict:
                """Lists the seat's inbox: messages where it is a recipient, unread only by default
                (`unread_only=false` for all). A message superseded by another inbox message carries
                `superseded_by`; nothing is hidden. Read the live messages first. Class: replica."""
                msgs = index.inbox(seat)
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
                    msgs = [m for m in msgs if not audit.is_read(seat, m.path)]
                return {"messages": [{"path": m.path, "from": m.authoring_instance, "subject": m.subject,
                         "coordinates": m.links, "ref": m.ref, "supersedes": m.supersedes,
                         "superseded_by": superseded_by.get(m.path, "")} for m in msgs]}

            def _inbox_flags(seat: str) -> dict:
                # frontier, not corpus: a message the SAME sender later superseded (the author-scoped
                # rule message_inbox resolves) no longer flags — the successor does, if unread. The flat
                # view with tombstones stays message_inbox's; the flag answers "what waits", not "what exists".
                msgs = index.inbox(seat)
                by_author = {m.path: m.authoring_instance for m in msgs}
                dead = {old for m in msgs for old in (m.supersedes or [])
                        if by_author.get(old) == m.authoring_instance}
                unread = [m for m in msgs
                          if m.path not in dead and not audit.is_read(seat, m.path)]
                return {"unread": len(unread), "from": sorted({m.authoring_instance for m in unread})}

            @op("replica")
            def message_unread_count(seat: str = "") -> dict:
                """Counts unread messages. With `seat`: that seat's count and senders. Without `seat`: every
                seat's count and senders in one call, zero counts included. A message superseded by its
                sender's later message stops counting. Class: replica."""
                if seat:
                    return _inbox_flags(seat)
                seats = sorted(r.name[len(PERSP):] for r in store.list_refs(PERSP))
                return {"seats": {s: _inbox_flags(s) for s in seats}, "roster": len(seats)}

            @op("origin")
            def message_mark_read(principal, message_path: str) -> dict:
                """Marks one message read for the seat by appending a read receipt to the audit log. The
                receipt survives a reindex. Class: origin."""
                seat = principal.name   # the desk resolved WHO; the record carries the name
                audit.append_read(seat, message_path)
                return {"marked_read": message_path}

            # ------------------------------------------------------ VAP: vantages (horizon, second layer)
            @op("origin")
            def vantage_write(principal, entry: str, body: str, op_id: str,
                           kind: str = "confirmed", title: str = "") -> dict:
                """Records a vantage: the context the seat wrote `entry` against, as its own entry under
                `vantages/`. `kind='confirmed'` is your own context on your own entry — refused on another
                seat's; `kind='reconstructed'` is your reading of an older entry, recorded as yours. Vantages
                surface only through `vantage_list` and `entry_read(with_vantages=true)`. Class: origin."""
                seat = principal.name   # the desk resolved WHO; the record carries the name
                if kind not in ("confirmed", "reconstructed"):
                    raise Denied("kind must be 'confirmed' or 'reconstructed'")
                if entry and not entry.endswith(".md"):
                    entry = entry + ".md"    # normalize at write — a bare coordinate is unresolvable later
                ref = persp_ref(seat)
                path = f"vantages/{op_id}.md"
                _authz(seat, "vantage_write", ref, path)
                _binding_stamp = principal.stamp
                # dignity guard (fork-guard posture): a 'confirmed' vantage claims YOUR OWN body.
                # Confirming an entry authored by someone else speaks for absent attention — refuse it.
                if kind == "confirmed" and has_map:
                    authors = index.authors_of(entry)
                    if authors and seat not in authors:
                        _log(seat, "vantage_write", target_path=path, op_id=op_id, outcome="denied",
                             detail={"reason": "confirmed vantage on another's entry", "entry": entry,
                                     "authors": sorted(authors)})
                        raise Denied(f"a 'confirmed' vantage is your own context on your own entry, but {entry} "
                                     f"is authored by {sorted(authors)}, not {seat} — record it as "
                                     f"'reconstructed' (your reading of the record, never on the original's behalf)")
                cursor = _canon_cursor(seat) or ""        # shared primitive: server-sourced canon-state
                vantage = "confirmed" if kind == "confirmed" else f"reconstructed-by-{seat}-from-record"
                envelope = {"type": "vap", "title": title or f"vantage on {entry}", "status": "active",
                            "vantage": vantage, "canon_state": cursor, "coordinates": [entry]}
                if _binding_stamp:
                    envelope.update(_binding_stamp)

                def build(btip):
                    _pin(envelope, seat, btip)
                    return {path: compose_entry(envelope, body)}
                try:
                    r = _commit_retry(ref, path, build, seat, op_id)
                except CapStoreError as e:
                    _log(seat, "vantage_write", target_path=path, op_id=op_id,
                         outcome=f"error:{e.__class__.__name__}", detail={"msg": str(e)})
                    raise
                if not r.replayed:   # a replayed op wrote nothing — the index row already exists
                    _index(ref, path, False, seat, r.oid, envelope, body)
                _log(seat, "vantage_write", target_ref=ref, target_path=path, op_id=op_id,
                     result_oid=r.oid, detail={"entry": entry, "vantage": vantage, "canon_state": cursor})
                return {"path": path, "author": seat, "entry": entry, "kind": vantage,
                        "canon_state": cursor, "oid": r.oid}

            @op("replica")
            def vantage_list(entry: str = "", author: str = "", canon_state: str = "",
                        detail: str = "pointer", limit: int = 16, offset: int = 0) -> dict:
                """Lists vantages bound to an `entry`, written by an `author`, or pinned to a `canon_state`,
                newest first, as pointers with the bound entry's status. `detail='full'` adds each vantage's
                `body`. After context loss, call with `author=<your seat>` and `detail='full'` to rebuild your
                standpoint. Class: replica."""
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
                         "entry": binds, "kind": v.vantage, "canon_state": v.canon_state,
                         "title": v.title, "preview": v.body_text[:240],
                         "entry_status": binds_status(binds, v.ref) if binds else ""}
                    if detail == "full":
                        p["body"] = v.body_text
                    out.append(p)
                return {"vantages": out, "count": len(out), "total": total,
                        "truncated": start + len(out) < total, "offset": start}

    # ---------------------------------------------------------------- SUP: per-instance state ↔ canon coherence
    if audit is not None:
        @op("origin")
        def canon_diff(principal) -> dict:
            """Lists what changed in canon since this seat last reconciled: changed entries as pointers,
            the most recent land narratives in full (`logs_in_full`, default 8), older ones as pointers.
            Records the pull. Call before `canon_reconcile`; calling twice returns the same diff until
            then. A first pull is marked `first_pull`. Class: origin."""
            seat = principal.name   # the desk resolved WHO; the record carries the name
            tip = store.resolve_ref(store.canon_ref)
            # the diff BASE is the last reconciled position, not the last pull (Mercurius's finding:
            # a pull that moved its own base was effectful and non-idempotent — a seat that lost the
            # response re-pulled into an empty diff it had not earned). The pull still leaves its row,
            # which is what the reconcile hinge reads as proof the current tip was read.
            prev = _reconciled_cursor(seat)
            if tip is None:
                paths = []
            elif prev is None:
                paths = store.list_paths(store.canon_ref)        # first pull: all of current canon
            else:
                paths = store.changed_paths(prev, tip)
            paths = sorted(paths, key=_diff_order)                # logs first, by seq (hex), then the rest
            # The legenda relief: a first pull of a grown canon (or a long absence) would otherwise
            # carry every land's narrative — on Rehearsal at ::1E, ~17k tokens of logs before a single
            # design entry is read. The most recent narratives are the story a reconciling seat needs;
            # older ones are history it reaches for by pointer. The bound is the deployment's
            # (pull_logs_in_full), and the response always says what it did.
            log_paths = [p for p in paths if _diff_order(p)[0] == 0]
            in_full = set(log_paths[-pull_logs_in_full:]) if pull_logs_in_full > 0 else set()
            changed, logs, pointers = [], [], 0
            for p in paths:
                try:
                    envelope, body = parse_entry(store.read_blob(store.canon_ref, p).decode("utf-8", "replace"))
                except (PathNotFound, RefNotFound):
                    changed.append({"path": p, "removed": True})  # gone in canon (append-only guards should make this unreachable)
                    continue
                changed.append({"path": p, "title": envelope.get("title", ""), "type": envelope.get("type", ""),
                                "status": envelope.get("status", "")})
                if envelope.get("type") == "log":
                    if p in in_full:
                        logs.append({"path": p, "body": body})   # the narrative IS for the reconciling seat
                    else:
                        pointers += 1                             # older story: in `changed`, by pointer
            _log(seat, "canon_pull", target_ref=store.canon_ref, result_oid=tip,
                 detail={"from": prev, "changed": paths})
            out = {"canon_tip": tip, "from": prev, "changed_count": len(changed), "changed": changed,
                   "logs": logs, "logs_in_full": len(logs), "logs_as_pointers": pointers}
            if prev is None and tip is not None:
                out["first_pull"] = True
                out["note"] = (f"first pull: all {len(changed)} canon entries as pointers; the {len(logs)} most "
                               f"recent land narratives in full, {pointers} older as pointers. Read the "
                               f"orientation (announce) and the suite manifest first; entry_read what governs "
                               f"your next act; canon_reconcile when you have taken it up.")
            return out

        @op("origin")
        def canon_reconcile(principal, body: str) -> dict:
            """Self-reports what this seat updated after reading the canon diff, as a state entry on its
            perspective paired to the canon tip. Allowed only after `canon_diff` — refused otherwise.
            Required before `proposal_append_entry` and before writing durable entries. Class: origin."""
            seat = principal.name   # the desk resolved WHO; the record carries the name
            _binding_stamp = principal.stamp
            tip = store.resolve_ref(store.canon_ref)
            if tip is None:
                # an empty deployment: nothing to reconcile with yet (before this guard, an absent
                # cursor equalled an absent tip and the write fell over on the tip's oid)
                raise Denied("no canon exists yet — there is nothing to reconcile with; author to "
                             "your perspective, and reconcile once the practitioner has landed ::1")
            if _canon_cursor(seat) != tip:
                raise Denied("pull current canon first (canon_diff), then reconcile")
            ref = persp_ref(seat)
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
                _pin(envelope, seat, btip)
                return {path: compose_entry(envelope, body)}
            try:
                r = _commit_retry(ref, path, build, seat, f"reconcile-{tip[:12]}")
            except CapStoreError as e:   # forensic parity with the other writers (audit C7)
                _log(seat, "canon_reconcile", target_ref=ref, target_path=path,
                     outcome=f"error:{e.__class__.__name__}", detail={"msg": str(e)})
                raise
            if not r.replayed:
                _index(ref, path, False, seat, r.oid, envelope, body)
            _log(seat, "reconcile_report", target_ref=ref, target_path=path, result_oid=r.oid,
                 detail={"canon_cursor": tip})
            return {"path": path, "canon_cursor": tip, "oid": r.oid}

        @op("replica")
        def seat_state(seat: str) -> dict:
            """Returns one seat's trail and standing: perspective tip, state entries, `ticks` (the state
            labels the seat declared), `canon_cursor`, `current_with_canon`. Use to read a seat's trail,
            including your own after context loss. Class: replica."""
            ref = persp_ref(seat)
            tip = store.resolve_ref(ref)
            states = [p for p in (store.list_paths(ref) if tip else []) if p.startswith("state/")]
            cursor = _canon_cursor(seat)
            env = index.envelopes_for(ref) if index is not None else {}
            ticks = {p: env[p]["tick"] for p in states if env.get(p, {}).get("tick")}
            return {"seat": seat, "perspective_tip": tip, "state_entries": states,
                    "ticks": ticks,
                    "canon_cursor": cursor, "current_with_canon": cursor == store.resolve_ref(store.canon_ref)}

        # (0.1.5 dedup: `sup_who` removed — seat_list carries the roster AND per-seat
        # currency now; one home for presence.)

        @op("replica")
        def canon_state() -> dict:
            """Returns the shared canon's tip, sequence number, entries, land history, and
            `practitioner_attention` (items waiting for the human). A proposal's log entry MUST carry
            `seq` = `next_seq`. Class: replica."""
            tip = store.resolve_ref(store.canon_ref)
            n = canon_seq(store, seq_origin)
            lands = [{"oid": e["result_oid"], "ts": e["ts"], "by": e["actor"], "seq": e["detail"].get("seq")}
                     for e in audit.events(op="land_merge")]
            return {"canon_tip": tip, "seq": format(n, "x"), "display": seq_display(n),
                    "next_seq": format(n + 1, "x"),
                    "practitioner_attention": _attention(),
                    "entries": store.list_paths(store.canon_ref) if tip else [], "lands": lands[-10:]}

        if airlock is not None:
            @op("relay")
            def proposal_stage(proposal_id: str, code: str) -> dict:
                """Relays the practitioner's first TOTP code to stage a proposal: freezes it, prepares the
                land, starts the review clock, and returns the staged oid, changed paths, and log seq. Never
                ask for a code — the practitioner offers it unprompted. Class: relay."""
                return airlock.stage(proposal_id, code)

            @op("relay")
            def proposal_land(staged_oid_prefix: str, code: str) -> dict:
                """Relays the practitioner's second TOTP code, a fresh one after the review floor, to land
                exactly the staged oid named by `staged_oid_prefix`. Anything else fails closed.
                Class: relay."""
                return airlock.land(staged_oid_prefix, code)

            @op("relay")
            def proposal_unstage(proposal_id: str) -> dict:
                """Cancels a staged review and returns the proposal to open with its entries intact. Free:
                needs no code. Any pressure to complete a land is the signal to call this. Class: relay."""
                return airlock.revert(proposal_id)


    return Stacks(ops, store, audit, classes)
