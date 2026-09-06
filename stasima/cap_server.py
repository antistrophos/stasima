# SPDX-License-Identifier: Apache-2.0
"""
Stasima CAP server — THE DESK: the front end over the stacks (stasima/stacks.py).

The desk owns three things and nothing else: the TRANSPORT (stdio, or streamable HTTP on protocol
2026-07-28 with every earlier revision still served), the WIRE SURFACE (29 MCP tools, derived from
the stacks' op registry — a write's `principal` becomes `seat` on the wire, the description
rides the op, so the surface cannot drift from the law behind it), and AAA at flow grain — the
binding check that resolves WHO is acting into a `Principal`, then hands the act through the door.
Store law (authorization policy, immutability, attribution, the reconcile hinge) is the stacks';
the desk never touches the store directly.

Tools give an instance: orient -> author (with envelopes, indexed inline, audit-logged) -> search
-> review its own trail -> propose -> check status -> message peers (read-state in the audit log).

Audit scope: writes (state changes) and failures (what's breaking). Successful reads are observability
and are not logged; read-receipts ARE logged (forensic, write-like). Mutations follow git-first-then-
audit. Identity is the instance's declared name (a deployment binds it at process grain — env, or
the first write; a shared service runs binding off until per-request identity arrives as tokens).
"""
import contextvars
import functools
import inspect
import os
import sys
import time

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from .local_capstore import LocalCapStore, PERSP_PREFIX as PERSP
from .map_index import SqliteMapIndex, StubEmbedder, LocalServerEmbedder
from .audit_log import SqliteAuditLog
from .authz import Denied, DefaultPolicy
from .stacks import build_stacks, Principal, Op
from .airlock import Airlock                             # TOTP two-phase remote approval
# re-exported through the server module for callers and tests that wire or read via it: the
# content model's serialization and the canon lifecycle (the cockpit, the airlock, the suite)
from .entries import compose_entry, parse_entry          # noqa: F401
from .canon import (CHAT_ERA_FREEZE, canon_seq, seq_display, reindex_from_git,   # noqa: F401
                   land_and_record, validate_log_entry, validate_log_entry as _validate_log_entry)


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
                 bound_instance: str = None, binding_mode: str = None,
                 port_token: str = None,
                 oauth_provider=None, public_url: str = None,
                 pull_logs_in_full: int = 8) -> MCPServer:
    _auth_kwargs = {}
    if oauth_provider is not None and public_url:
        # the OAuth door: the SDK mounts discovery + DCR + /authorize + /token + the bearer
        # middleware from these two kwargs; the provider (stasima.oauth) is the storage + the
        # TOTP-approval policy behind them. AS and RS are one server: issuer == the public host.
        from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
        _auth_kwargs = {"auth_server_provider": oauth_provider,
                        "auth": AuthSettings(issuer_url=public_url,
                                             resource_server_url=f"{public_url.rstrip('/')}/mcp",
                                             client_registration_options=ClientRegistrationOptions(enabled=True))}

    # The request seam (v2). The v1 server exposed the live request context as an attribute the
    # binding code read from anywhere; v2 hands it only to the handler. A server middleware sees
    # every inbound message with its context built, so it publishes the context in a contextvar
    # for the duration of the call — the handler runs inside call_next, in the same context, and
    # anyio carries contextvars into the worker thread a sync tool runs on. Outside a request the
    # var is None and the seam falls back to the process-wide session (stdio's one pipe).
    _current_request = contextvars.ContextVar("stasima_request", default=None)

    async def _publish_request(ctx, call_next):
        token = _current_request.set(ctx)
        try:
            return await call_next(ctx)
        finally:
            _current_request.reset(token)

    # host/port/transport-security are transport options in v2, not server identity: they ride
    # run() / streamable_http_app() in main(), where the config is. The tool list is fixed for the
    # life of the process (registrations happen here, once) and comes back in registration order —
    # deterministic, as the protocol asks — so it carries an honest cache hint: a client may hold
    # it for five minutes, which also bounds how long a restarted service with a changed surface
    # goes unnoticed. `private`: the list is the same for everyone, but no intermediary should
    # cache a knowledge server's surface on the fleet's behalf.
    from mcp.server import CacheHint
    mcp = MCPServer("stasima", middleware=[_publish_request],
                    cache_hints={"tools/list": CacheHint(ttl_ms=300_000, scope="private")},
                    **_auth_kwargs)

    def _class_kw(cls):
        """The class rides the wire three ways: the description's last sentence (for the model),
        the MCP annotations (for clients), and `meta.class` (for the reference generator)."""
        ro = cls in ("replica", "process")
        return dict(annotations=ToolAnnotations(read_only_hint=ro, destructive_hint=False,
                                                idempotent_hint=ro, open_world_hint=False),
                    meta={"class": cls})

    def tool(**kw):
        """The SDK's tool decorator with errors-as-instructions preserved. The 2.1 SDK renders a `ToolError`
        with its own message but wraps any OTHER exception first, so a refusal raised as `Denied`
        (or a store error) would reach the seat as the wrapper's text — and every recover routine
        the docks teach reads the refusal's sentence. So each tool lifts what it raises into a
        `ToolError` carrying that sentence: a `Denied` verbatim (its message is already the
        instruction), anything else prefixed with its class (the shape of the fault)."""
        def deco(fn):
            @functools.wraps(fn)
            def instructive(*a, **k):
                try:
                    return fn(*a, **k)
                except ToolError:
                    raise
                except Denied as e:
                    raise ToolError(str(e)) from e
                except Exception as e:
                    raise ToolError(f"{type(e).__name__}: {e}") from e
            return mcp.tool(**kw)(instructive)
        return deco

    # Binding — the SSH-shaped identity pin, with STICKY learning (port-security with sticky MACs;
    # OPERATIONS, "Seat identity"), at PROCESS grain. The ruling behind the grain (the v2 port,
    # "demote deliberately"): protocol 2026-07-28 has no per-conversation session to bind — the
    # spec removed sessions, and even a handshake-era client is handed a fresh session object per
    # request — so binding keeps the grains where enforcement always worked. Sources, strongest
    # first: STASIMA_INSTANCE (pinned — pre-seeded, no learning), a PORT-learned binding
    # (STASIMA_PORT names this definition; the learned name persists as append-only port_binding
    # events in the audit log — the ledger IS the running config, and the console clears it), a
    # PROCESS-learned binding (no port: the first identity-claiming WRITE binds this process for its
    # lifetime; the rekey is a new process — under stdio the client spawned this process, so that
    # is one conversation). Modes (STASIMA_BINDING): strict = mismatched writes refuse — THE
    # DEFAULT: secure unless the server's owner explicitly downgrades; witness = proceed and
    # confess (authored_via in the envelope + an audit row); off = the explicit rip-cord — no
    # learning, no enforcement, the HTTPS-to-HTTP downgrade, server-owned and never callable from
    # the wire. A SHARED service (the http transport) must not learn — it would bind the whole
    # fleet to its first writer — so server_from_config refuses to start one that could; per-
    # request identity for a shared service arrives as tokens (the port's auth phase). Reads are
    # never guarded (pull model; the corpus is world-readable).
    if bound_instance is not None and not str(bound_instance).strip():
        bound_instance = None
    if port_token is not None and not str(port_token).strip():
        port_token = None
    binding_mode = (binding_mode or "strict").lower()
    if binding_mode not in ("strict", "witness", "off"):
        raise ValueError(f"binding_mode must be strict|witness|off, got {binding_mode!r}")

    _binding = {"name": None, "source": None}   # this process's learned (or port-restored) binding

    def _session_tag():
        """Observability, never enforcement: the transport session a request rode in on — a
        handshake-era client's Mcp-Session-Id (the bridge's protocol), 'stateless' for the modern
        protocol (it has no session to name), None on stdio and in-process. Rides every audit row
        from the http transport, so "writes on your branch from sessions other than yours" stays
        a query even though nothing binds to it."""
        ctx = _current_request.get()
        req = getattr(ctx, "request", None) if ctx is not None else None
        if req is None:
            return None
        try:
            sid = req.headers.get("mcp-session-id")
        except Exception:
            sid = None
        return f"s{sid[:8]}" if sid else "stateless"

    def persp_ref(iid): return PERSP + iid

    def _log(actor, op, **kw):
        # the desk's own audit rows (binding events, refusals at the door) — labelled with the
        # transport session exactly as the stacks label theirs
        if audit is not None:
            tag = _session_tag()
            if tag:
                d = dict(kw.get("detail") or {})
                d.setdefault("session", tag)
                kw["detail"] = d
            audit.append(actor, op, **kw)

    def _check_binding(claimed, op, ref=None, path=None):
        """Identity-claiming WRITES check their claimed name against this process's binding —
        pinned (env), port-learned (durable sticky), or process-learned (the first write binds).
        Returns the witness stamp ({'authored_via': <bound name>}) when the caller should stamp an
        envelope, else None. Every witness mismatch leaves an audit row here regardless of whether
        the op writes an envelope — the confession is never optional, only its git copy is. (The
        audit op names `session_binding` / `port_binding` are ledger vocabulary from the era that
        bound per transport session; they stay, so the rotation history reads as one trail.)"""
        if binding_mode == "off":
            return None                                    # the explicit, server-owned rip-cord
        bound = bound_instance or _binding["name"]
        if bound is None:
            # sticky learn: the first identity-claiming write binds this PROCESS — and, through
            # a port, the definition (durably: the learn is an append-only event the console clears)
            _binding.update(name=claimed, source="port" if port_token else "process")
            detail = {"mode": binding_mode, "source": _binding["source"], "learned": True}
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
            raise Denied(f"this server process is {how} '{bound}' (strict). To act as '{claimed}': use "
                         f"that seat's own server process, or the practitioner downgrades this "
                         f"process (STASIMA_BINDING=witness, or a console `binding --clear` on "
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
            _binding.update(name=_prior, source="port")   # the definition learned; this process inherits
            _log(_prior, "session_binding", detail={"mode": binding_mode, "source": "port",
                                                    "port": port_token, "restored": True})

    @tool(**_class_kw("process"))
    def seat_whoami(seat: str) -> dict:
        """Reports how this server process sees the seat: its perspective ref, the tools it may
        write with, and the process's binding (`mode`, `grain`, `bound_seat`, `source`, `match`).
        `match` is true when `seat` is the bound one, false when another seat is, and null when
        nothing is bound (`mode='off'`, or nothing learned yet): three states, not two. `tools` is
        the count and names this server offers; compare it against what the client loaded before
        calling a tool missing. Use before writing when identity is in doubt. Class: process."""
        out = {"seat": seat, "perspective_ref": persp_ref(seat),
               "namespace": f"perspectives/{seat}", "allowed_ops": ["entry_write", "proposal_append_entry", "message_send", "vantage_write"],
               "note": "identity is a recorded name; the binding (pinned or sticky-learned, at process grain) guards writes"}
        eff = bound_instance or _binding["name"]
        sb = {"mode": binding_mode, "grain": "process", "bound_seat": eff,
              "source": "pinned" if bound_instance else _binding["source"],
              "match": (seat == eff) if eff else None}
        if port_token:
            sb["port"] = port_token
        out["tools"] = {"count": len(_surface), "names": list(_surface)}
        out["binding"] = sb
        return out


    # ---------------------------------------------------------------- the desk over the door
    # One MCP tool per op, its wire signature DERIVED from the handler's: a write's `principal`
    # becomes `seat: str` on the wire, a read's signature passes through. The description rides the op. So the tool surface
    # cannot drift from the registry, and the desk's only work per write is AAA — resolve WHO
    # (the binding check, in witness mode the stamp) and hand the act through the door.
    S = build_stacks(store, index, embedder, audit, authz, airlock,
                     orientation_text=orientation_text, orientation_base=orientation_base,
                     seq_origin=seq_origin, deployment_name=deployment_name,
                     pull_logs_in_full=pull_logs_in_full)

    ARRIVAL = {"seat_announce"}   # writes that take a principal but run before any binding exists

    def _principal(name, opname, ref=None, path=None):
        stamp = _check_binding(name, opname, ref, path)
        return Principal(name=name, stamp=stamp,
                         source=("off" if binding_mode == "off" else
                                 "pinned" if bound_instance else _binding["source"] or "unbound"),
                         session=_session_tag())

    def _target(name, opname, k):
        # the coordinates the binding audit rows name (target_ref / target_path), by op shape
        ref = persp_ref(name)
        if "domain" in k and "slug" in k:
            return ref, f"{k['domain']}/{k['slug']}.md"
        if opname == "message_send":
            return ref, f"messages/{k.get('op_id', '')}.md"
        if opname == "vantage_write":
            return ref, f"vantages/{k.get('op_id', '')}.md"
        if opname == "message_mark_read":
            return None, k.get("message_path")
        if opname == "proposal_close":
            return ref, f"close/{k.get('proposal_id', '')}"
        if "path" in k:
            return ref, k["path"]
        return (ref if opname != "canon_diff" else None), None

    def _adapter(opname, fn):
        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        if opname in S.writes:
            wire = [inspect.Parameter("seat", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str)]
            wire = wire + params[1:]

            def adapter(**k):
                who = k.pop("seat")
                if opname in ARRIVAL:
                    # arrival claims a name; nothing is verified until the first identity-claiming
                    # WRITE (the guard's own rule) — so the door gets the claim, marked as a claim
                    p = Principal(name=who, stamp=None, source="claimed", session=_session_tag())
                else:
                    ref, path = _target(who, opname, k)
                    p = _principal(who, opname, ref, path)
                return S.apply(p, Op(opname, k, k.get("op_id")))
        else:
            wire = params

            def adapter(**k):
                return S.call(opname, **k)
        adapter.__name__ = adapter.__qualname__ = opname
        adapter.__doc__ = fn.__doc__
        adapter.__signature__ = sig.replace(parameters=wire)
        adapter.__annotations__ = {p.name: p.annotation for p in wire
                                   if p.annotation is not inspect.Parameter.empty}
        adapter.__annotations__["return"] = sig.return_annotation
        return adapter

    for _name, _fn in S.ops.items():
        tool(**_class_kw(S.classes.get(_name, "origin")))(_adapter(_name, _fn))
    # the surface this process offers, as seat_whoami reports it: the registry plus the desk's own
    # tool — a seat inside a client that dropped a tool can tell a client gap from a build gap
    # (parallax's fresh-seat finding, 2026-09-06)
    _surface = sorted(list(S.ops) + ["seat_whoami"])

    if oauth_provider is not None and public_url:
        # the practitioner's side of the door: the SDK redirected the browser here; the SAME TOTP
        # that gates canon approves the connector (no passwords, no accounts — presence-proof)
        from starlette.requests import Request
        from starlette.responses import HTMLResponse, RedirectResponse

        from .oauth import approve_page

        async def _approve_target(p):
            # what the practitioner must see before approving: the requesting client and the exact
            # redirect the code will be sent to (the confused-deputy check)
            client = await oauth_provider.get_client(p["client_id"])
            name = (client.client_name if client and client.client_name else p["client_id"])
            return name, str(p["params"].redirect_uri)

        @mcp.custom_route("/approve", methods=["GET", "POST"])
        async def _approve(request: Request):
            if request.method == "GET":
                txn = request.query_params.get("txn", "")
                p = oauth_provider.pending(txn)
                if p is None:
                    return HTMLResponse("this approval request expired — retry from the client",
                                        status_code=400)
                if p["redirect"]:   # approved from the console — the polling page follows home
                    return RedirectResponse(p["redirect"], status_code=302)
                name, ruri = await _approve_target(p)
                return HTMLResponse(approve_page(txn, name, ruri))
            form = await request.form()
            txn = str(form.get("txn", ""))
            p = oauth_provider.pending(txn)
            if p is None:
                return HTMLResponse("expired — retry from the client", status_code=400)
            if p["redirect"]:
                return RedirectResponse(p["redirect"], status_code=302)
            w = oauth_provider.totp_window(str(form.get("code", "")))
            if w is None:
                left = oauth_provider.record_miss(txn)   # burn the txn after too many wrong codes
                if left <= 0:
                    return HTMLResponse("too many wrong codes — this request is closed; retry from "
                                        "the client for a fresh one", status_code=429)
                name, ruri = await _approve_target(p)
                return HTMLResponse(approve_page(txn, name, ruri,
                                    error=f"code refused — {left} attempt(s) left before this "
                                          f"request closes; try the NEXT code"), status_code=401)
            return RedirectResponse(oauth_provider.grant(txn, w), status_code=302)

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


def server_from_config(cfg) -> MCPServer:
    """Assemble the MCP server from a Config."""
    store, index, embedder, audit, authz, airlock = components_from_config(cfg)
    _bound = os.environ.get("STASIMA_INSTANCE") or None
    _mode = (os.environ.get("STASIMA_BINDING") or getattr(cfg, "binding_mode", "") or "strict").lower()
    if cfg.transport == "http" and _mode != "off" and not _bound:
        # A shared service that could LEARN would bind the whole fleet to its first writer (the
        # trunk problem, made structural): the protocol has no per-conversation session for the
        # binding to attach to. The honest configurations are: off (attribution still rides every
        # write), or pinned (STASIMA_INSTANCE makes the service one seat's own door).
        from .config import ConfigError
        raise ConfigError(f"transport = \"http\" with binding_mode = {_mode!r} and no STASIMA_INSTANCE: "
                          "a shared http service has no per-conversation session to bind (protocol "
                          "2026-07-28), so sticky learning would bind the whole service to its first "
                          "writer. Set binding_mode = \"off\" in the http toml (attribution rides every "
                          "write regardless), or pin the service to one seat with STASIMA_INSTANCE.")
    oauth_provider = None
    if getattr(cfg, "http_public_url", ""):
        from .oauth import StasimaOAuth
        oauth_provider = StasimaOAuth(cfg.resolved_auth_db(),
                                      cfg.resolved_airlock_secret(), audit=audit)
    return build_server(store, index, embedder, audit, authz, airlock,
                        oauth_provider=oauth_provider,
                        public_url=cfg.http_public_url or None,
                        orientation_base=cfg.orientation_base, seq_origin=cfg.seq_origin,
                        deployment_name=cfg.deployment_name,
                        pull_logs_in_full=int(getattr(cfg, "pull_logs_in_full", 8)),
                        # binding rides ENV, not the shared config file: the config is one file for
                        # every seat's definition; the env is what distinguishes definitions
                        bound_instance=_bound,
                        # env overrides the config field; config lets the http toml carry it (a
                        # shared service sets binding_mode = "off" — guarded above)
                        binding_mode=_mode,
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
        # The loopback/tailnet bind is defense-in-depth; the OAuth door (when http_public_url is
        # set) is the real perimeter, reached via `tailscale serve`/`funnel` proxying to loopback.
        # v2: the bind and the DNS-rebinding allowlist are transport options passed here, not at
        # construction. A v2 server serves every earlier protocol revision, so handshake-era
        # clients (the mcp-proxy bridge) keep connecting unchanged.
        _ts = _transport_security(_cfg.http_host, _cfg.http_allowed_hosts)
        _stateless = bool(getattr(_cfg, "http_stateless", False))
        if getattr(_cfg, "http_public_url", ""):
            # public/authed: wrap the whole app in the hardening middleware (Host allowlist over
            # the credential routes, body cap, per-IP rate limit, security headers) — the SDK's
            # transport-security guards only /mcp. Then run uvicorn on the wrapped app. The SDK
            # app's own lifespan (its session manager) still runs: the middleware forwards every
            # non-http scope to it untouched.
            import uvicorn
            from .http_guard import harden
            app = harden(_srv.streamable_http_app(transport_security=_ts, stateless_http=_stateless),
                         allowed_hosts=_cfg.http_allowed_hosts)
            uvicorn.Server(uvicorn.Config(app, host=_cfg.http_host, port=_cfg.http_port,
                                          log_level="info")).run()
        else:
            _srv.run(transport="streamable-http", host=_cfg.http_host, port=_cfg.http_port,
                     transport_security=_ts, stateless_http=_stateless)
    else:
        _exit_when_parent_dies()   # stdio: the client spawned us; if it dies, don't orphan
        _srv.run()                 # stdio: the connecting client spawns this process


if __name__ == "__main__":
    main()
