# Changelog

All notable changes to the Stasima suite. The suite follows the practice's own discipline: entries
are added, never rewritten — corrections appear as later entries.

## Unreleased

- **The suite runs in parallel, times itself, and takes filters.** `run_tests.py` runs the 24
  standalone tests four at a time by default (`-j N`; `--serial` is the old behavior) and prints
  each test's wall time plus the three slowest: on the build machine 183 s of wall for 694 s of
  test time, against ten-plus minutes serial. `-k <substring>` (repeatable) runs one test or one
  family. The measurement it produced: the cost is git subprocess spawns — the three slowest tests
  are the ones that commit most — at roughly a quarter second per spawn on Windows, which is a
  store-level fact for a later window, not a suite one.

- **`_testkit.py` — the suite's shared helpers.** The result reader (`payload`), the refusal
  readers (`is_err`, `err_text`, `text`), a fresh bare repo (`fresh_repo`), and the free-port /
  wait-for-port pair the transport tests use. Nine tests carried their own copies, in four slightly
  different shapes; they import one now. Tests stay standalone scripts. Unused imports the dedupe
  left behind are pruned.

- **CI on every push, on both platforms, on Node 24 actions.** Before 0.2.1 the suite ran in CI only
  at release time (the 0.2.0 branch had no CI at all until its tag). New `ci.yml` runs test + build
  on every push and pull request, on Ubuntu with Python 3.12 (the package's floor) and on Windows
  with Python 3.14 (the reference fleet's shape — the stdio hang and the read-only git-object
  regressions only show there). Both workflows pin the Node 24 majors (checkout v7, setup-python
  v7, upload-artifact v7, download-artifact v8): GitHub removes Node 20 from its runners on
  2026-09-23, and the 0.2.0 release run carried the deprecation warning.

## 0.2.0 — 2026-09-05 (the MCP v2 port: SDK 2.1 on protocol 2026-07-28 with every earlier revision served; the desk-and-stacks split; stateless http; soaked on the live fleet before tagging)

- **Soaked before tagging.** Cut over on the Rehearsal fleet at 2026-09-05T00:28Z and held there
  while three seats reported from their own chairs (the record is on the merge PR): the pull
  measured from the last reconcile, the earned empty map, the first in-the-wild observation of
  the idempotent re-pull, refusals arriving as their own sentences, the `binding` block as
  specified, every message attributed through `instance_id` under the stateless service. Two
  findings, both fixed before the tag: the reconcile dock had not named the pull's new return
  fields (reconcile-v3 landed as canon ::1F; skill regenerated), and one client held a stale
  0.1.5 skill archive (re-uploaded). Nothing read wrong at the wire.

- **The legenda relief: `canon_diff` bounds the narratives it carries in full.** The legenda
  criterion (canon ::13) names the failure — a canon no longer readable entire — and the practitioner
  reported it firing on Rehearsal: a fresh seat's first pull was too large to read as content, so fresh
  seats read titles. Measured at ::1E: 106 entries, ~159k tokens of canon; a first pull carried all
  30 land narratives in full, ~17k tokens of logs plus ~4k of pointers before one design entry was
  read. Now the pull carries the most recent `pull_logs_in_full` narratives in full (new toml field,
  default 8; on Rehearsal ~6.7k tokens instead of ~17k) and older logs as pointers in the map, and the
  response says what it did: `logs_in_full`, `logs_as_pointers`, and on a first pull `first_pull:
  true` with a `note` naming the reading order (orientation, the suite manifest, then what governs
  your next act). The map itself is never bounded — every changed entry is still a pointer; a seat
  eight lands behind or fewer sees every narrative, exactly as before. `stacks_test` proves the bound
  at 2 and at 0. This is relief inside one canon; the structural answer is the area split the
  subsidiarity design already describes, drafted at the seat's grain on epode's branch
  (technical/seat-across-canons-home-and-memberships.md) for a review round.

- **The 0.2.0 polish pass — the documents say what the code does.** STATUS, ARCHITECTURE (the
  trust model, the HTTP era, four new invariants — store law behind the door, the derived wire
  surface, fast-forward-only carriers — and the two doors as extension points), SETUP, README,
  OPERATIONS' rekeying note, the cockpit's screen title, and the binding test's title all describe
  binding at process grain and the desk-and-stacks shape; nothing left says "session binding"
  except the ledger's own op names. `skills/gen_aous.py` now follows canon's supersession from a
  dock's home path to its living edition, so a dock revised at a new path (the 0.2.0 `canon_diff`
  semantics want one) is picked up by regeneration without touching the generator; regenerated
  from live canon today it is byte-identical; `--ref refs/cap/proposals/<id>` previews the encoding a
  staged proposal would produce, so the gate can read the skill diff before the land (the 0.2.0
  dock editions preview as 22 lines in reconcile, 8 in recover, nothing else). Two `server_test`
  assertions the phase-one rename
  had missed (multi-line `getattr(..., "isError", False)`) were passing vacuously and now check
  `is_error`. Unused imports pruned from the desk and the stacks; the desk's re-exports (the
  content model's serialization, the canon lifecycle) are marked as such. `bridge_smoke.py` ships
  in the sdist.

- **The MCP v2 port, phase four: stateless http, measured against the real bridge; the tool list
  carries a cache hint; the cockpit learns the venv.** `http_stateless = true` (new toml field,
  default off) serves every request on a fresh transport with no `Mcp-Session-Id` — the protocol
  has none since 2026-07-28, and this stops offering one to handshake-era clients too. The prize
  the early-port clause named: **a service can restart under open bridges without terminating
  them.** `bridge_smoke.py` (new; the pre-cutover check, not part of the suite — it needs the
  deploying machine's own `mcp-proxy`) drives the ported server through the REAL bridge (mcp
  1.28.1 / mcp-proxy 0.12.0, in the other interpreter) in both modes, then restarts the service
  under the open bridge: sessions `survives-restart=NO` ("Session terminated"), stateless `YES`.
  The cost is one forensic label (legacy clients' audit rows read `session: stateless`). The
  restart rule in OPERATIONS is now conditional on the mode, and the cutover runbook is written.
  `tools/list` carries `ttlMs 300000 / cacheScope private` (the surface is fixed per process and
  comes back in registration order — deterministic, as the protocol asks; the http test checks
  both). `service_python` (new toml field) tells the cockpit which interpreter starts the service
  and drops `PYTHONPATH` for it, so a venv service cannot be shadowed by the launcher's source
  path — the knob the v2 deployment shape needs.

- **The MCP v2 port, phase two (second half): the desk-and-stacks split — a layer boundary
  between the front end and the store law.** `cap_server.py` is now THE DESK: transport, the
  29-tool wire surface, and AAA (the binding check resolves WHO into a `Principal`). New
  `stasima/stacks.py` is THE STACKS: every helper and every op body, moved verbatim, behind two
  doors and a read shelf — `apply(principal, op)` for an authored act, `advance_replica(carrier,
  ref, new, expected_old)` for a carrier's structural fast-forward (new store primitive
  `LocalCapStore.fast_forward`: CAS + fast-forward-only, bypasses the origin-only guard, never
  history), `call(name, ...)` for reads. Store law — authorization policy, immutability,
  attribution, thread form, the reconcile hinge — runs behind the door whoever knocks; the stacks
  know no transport. The desk's tool surface is DERIVED from the stacks' registry (a write's
  `principal` becomes `instance_id` on the wire; the description rides the op), so it cannot drift:
  `docs/tools.md` regenerated with NO diff for 28 of 29 tools. `stacks_test.py` drives both doors
  and the shelf with no MCP in the process — the proof the boundary is real. Two ride-alongs and one
  latent fix ride the move:
  - **`canon_diff` is idempotent until you reconcile** (Mercurius's finding): the diff is measured
    from the canon you last RECONCILED with, not from your last pull, so a lost response is re-pulled
    for free; the pull still leaves its row, which is what the reconcile hinge reads. (The one tool
    whose description changed.)
  - **Log entries lead the diff in sequence order** (Alidade's cold-arrival finding): git listed
    `meta/log/10.md` before `meta/log/2.md`; the pull now sorts logs by their hex value, then the
    rest in path order.
  - **Reconciling against an empty canon refuses with an instruction** instead of falling over on
    the missing tip (`None == None` passed the hinge before).
  Arrival (`announce`) reaches the door with a CLAIMED principal — nothing is verified until the
  first identity-claiming write, the guard's own rule, unchanged. AAA order at the desk is now
  authentication (binding) before authorization (policy); both refusals read as before.

- **The MCP v2 port, phase two (first half): binding demotes to PROCESS grain — the ruling
  ("demote deliberately", 2026-08-02) made code.** The protocol has no per-conversation session to
  bind: 2026-07-28 removed sessions, and phase one found that even a handshake-era client is handed
  a fresh session object per request. So the per-session sticky table phase one carried across is
  gone, and binding keeps exactly the grains where enforcement always worked — a pinned definition,
  a ported definition (durable sticky), and the process itself (stdio: the client spawned it, so
  that IS one conversation). Consequences, all shipped:
  - **A shared http service refuses to start if it could learn** (`strict`/`witness` with no
    `STASIMA_INSTANCE`): a service that learned would bind the whole fleet to its first writer —
    the trunk problem, now structural rather than a caution. The error names the fix (`off`, or
    pin). The fleet's own toml already runs `off`, so the live deployment needs no change.
  - **`whoami`'s block is `binding` (was `session_binding`) and carries `grain: "process"`**; a
    learned binding's `source` reads `process` (was `session`). Audit op names (`session_binding`,
    `port_binding`) are ledger vocabulary and stay, so the rotation trail reads as one history.
  - **The transport session survives as an audit LABEL, never as identity**: rows from the http
    transport carry `session: s<id>` for a legacy client and `stateless` for the modern protocol,
    so "writes on your branch from conversations other than yours" stays a query.
  - The http test now proves the three honest shared-service shapes end to end: `off` (two
    conversations, two seats, both write, attribution rides each envelope), strict-unpinned
    (refused at startup with the instruction), and pinned (one seat's door enforced over the
    modern protocol with no session at all). OPERATIONS and `docs/upgrading.md` (0.1.5 → 0.2.0)
    say the same thing the code does. Per-request identity for a shared service is the token door
    — the port's auth phase, not this one.

- **The MCP v2 port, phase one: the server runs on SDK 2.1 (`mcp>=2.1,<3`) — protocol
  2026-07-28 — and still serves every earlier revision.** The pin below is lifted. `FastMCP`
  becomes `MCPServer`; the bind address and the DNS-rebinding allowlist become transport options
  passed at `run()` / `streamable_http_app()` instead of construction; the suite drives the server
  through the SDK's one `Client` (in-process, stdio, and HTTP alike) and reads snake_case result
  fields (`is_error`, `structured_content`, `input_schema`). 23/23 green. Two things the suite
  forced into the open, both shipped here:
  - **Refusals stay instructions.** The 2.1 SDK renders a `ToolError` with its message but wraps
    any other exception first, so a `Denied` raised inside a tool would have reached the seat as
    the wrapper's text — and every recover routine the docks teach reads the refusal's sentence.
    Every tool now lifts what it raises into a `ToolError` carrying that sentence (a `Denied`
    verbatim; a store error prefixed with its class). The wire text is unchanged from 0.1.5
    (`Error executing tool <name>: <message>`); the suite's refusal assertions are the proof. This
    was the port's planned later phase, pulled forward because the suite cannot pass without it.
  - **The session seam keys on the transport's own session id.** v2 builds a fresh session object
    per request, even for a handshake-era client; the only conversation identity such a client
    carries is its `Mcp-Session-Id`, so sticky binding keys on that (a bounded table), stdio stays
    process-sticky, and a stateless modern-protocol request has no conversation to bind — its
    audit row says `stateless`. The http test arrives as both protocol eras and proves two legacy
    sessions bind two seats independently — the `mcp-proxy` bridge's case exactly.
  Deployment note for the cutover: do NOT install the SDK upgrade into the interpreter that runs
  the `mcp-proxy` bridge (it declares `mcp>=1.17.0` with no ceiling and predates v2); the ported
  service runs from its own venv. The cutover sequence lands in OPERATIONS before release.

- **`mcp` is pinned below 2.0** (`mcp>=1.10,<2`). The MCP 2026-07-28 protocol revision removed
  protocol-level sessions and the initialize handshake, and the SDK's same-day 2.0 release renames
  `FastMCP` to `MCPServer` and rebuilds the low-level server — the session-binding seam this suite
  attaches to does not survive it. Fresh installs were one resolver decision away from an import
  error; now they can't be. The v2 port is future deliberate work (stateless protocol,
  token-carried identity, CIMD authorization), tracked on the board — not something a floor
  constraint should be allowed to spring on an installer.

- **The HTTP transport's dependencies are declared** — `uvicorn`, `starlette`, and `httpx` are
  direct imports (the fleet server, its routes, the local-server embedder) that previously arrived
  only transitively via `mcp`; a direct import deserves a direct declaration, so an upstream
  dependency-tree change can never silently break the fleet's primary transport. The test suite's
  async harness gains a `[test]` extra (`anyio`), and CI installs it explicitly instead of
  inheriting it by luck.

## 0.1.5 — 2026-07-21 (the wire-lean release; the Aous suite and the HTTP era ship with it)

*Re-cut at tag time: an earlier in-tree form of this section (dated 2026-07-18) predated the HTTP
era and the hardening pass, and nothing published ever carried it — this records the release as it
actually ships.*

Four arcs in one line: the pre-load performance pass (substrate-internal, measured on the live
corpus), the identity layer (session binding, seat-found and practitioner-designed), the registry
dedup — six tools removed or folded because every desktop conversation carries the tool registry,
and weight there is paid by everyone on every turn — and the **HTTP era**: one continuously-running
fleet server with an OAuth door, closed out by an adversarially-verified hardening pass. 35 → 29
tools; the registry drops from ~7.7k to ~6.3k tokens with descriptions dieted to contract + dock
pointer (the deep teaching lives in the suites now — that is what suites are for). The **Aous**
skill suite (fifth river) carries the 0.1.5 contract; Aliakmon remains the 0.1.4 edition
(succession grows).

### Added — the HTTP era (one fleet server)
- **The `http` transport is fleet-grade** — `transport = "http"` runs ONE continuously-running
  server every instance connects to (`http://<host>:<port>/mcp`), each conversation its own
  streamable-HTTP session. The shared internals stdio never contended are locked for concurrent
  handler threads (audit append — a race would fork the hash chain — the cat-file sidecar's
  protocol, map-index writes, the binding registry), and every audit row from an HTTP session
  carries a session tag. Run it from a SEPARATE toml (flipping a shared stdio toml would make every
  spawned stdio child try to serve HTTP); OPERATIONS carries the runbook, including the restart
  sequence for bridge deployments.
- **Session binding becomes per-conversation under HTTP** — the binding seam keys on the transport
  session, so sticky learning lands at the granularity the desktop's shared process wanted: per
  conversation, not per process. Corollary, field-found twice: a definition that multiplexes many
  conversations onto ONE transport (the desktop's shared stdio process; an `mcp-proxy` bridge in
  front of the http service) is a TRUNK — the first seat's write binds it and every other seat's
  writes refuse. **Never sticky a trunk**: run binding off on that definition. Native
  per-conversation sessions get the enforcement for free.
- **`binding_mode` config field** — the toml now carries the server-wide session-binding mode
  (`"strict"` | `"witness"` | `"off"`; blank = strict, the default). `STASIMA_BINDING` still
  overrides. This is how a bridge deployment turns binding off without a user-wide env var.
- **The OAuth door** — setting `http_public_url` turns the authorization server ON: the MCP SDK
  mounts discovery + dynamic client registration + PKCE + the bearer requirement on `/mcp`;
  `stasima/oauth.py` is the provider behind them — client/token storage in `auth.sqlite` (beside
  the audit db, in the backup path) and the approval *policy*: the same TOTP that gates canon
  approves a connector, with the airlock's replay discipline. No passwords, no accounts —
  presence-proof. Blank `http_public_url` = loopback trust, unchanged.
- **The console approval channel** — pending OAuth authorizations persist in `auth.sqlite`, so the
  cockpit (a separate process on the same file) lists and approves them: presence at the terminal
  is the gate, no code spoken anywhere. The approve page polls and follows home on whichever
  channel grants first; every approval audit row names its channel.
- **The cockpit learns the fleet** — an HTTP service screen (status by port probe with the
  connector URL, one-key creation of the separate http toml, detached start with a pidfile, guarded
  stop, the OAuth status line + approvals review) and a Bindings screen (the sticky table, the
  binding trail, guarded rekey).
- **The SQLite stores open in WAL mode** (audit / map index / auth) — cross-process safety:
  rollback journals take whole-database exclusive locks, so a second process on the same file (a
  cockpit, a stray stdio server) could stall the fleet's writes. Operationally visible:
  `-wal`/`-shm` files appear beside the databases. `admin backup` is unaffected (it snapshots via
  SQLite's own backup API); hand-copies of a live database must include the sidecar files.
- Git children of the detached fleet service no longer flash console windows (CREATE_NO_WINDOW),
  and `announce`'s arrival text teaches the 29-tool registry it fronts — it still taught four
  removed tools, caught by an Aous-skilled seat reading its own arrival on the live server.

### Changed — BREAKING (the dedup; upgrading.md has the one-liners)
- **Removed `orientation`** — it returned one field of `announce`'s response. Call `announce`.
- **Removed `canon_head`** — a strict subset of `canon_state`. Call `canon_state`.
- **Removed `proposal_status`** — it kept the pre-lifecycle is-ancestor logic and answered
  strictly worse than `list_proposals` (open/landed/closed + lands_behind). The deep examination
  stays `conflict_preview`.
- **Removed `sup_who`** — `list_instances` now carries the roster AND `current_with_canon` per
  seat (additive key; the names list is unchanged).
- **Removed `my_perspective`** — `list_entries(ref=<your name>)` is the same enriched listing;
  your tip rides `announce` and `sup_state`.
- **Removed `imp_flags_all`** — `imp_flags` with NO `instance_id` is the roster glance (same
  return shape); with one, the single flag as before.

### Added
- **`perf_scry`** — the server-git boundary's complete ledger, metered at the one chokepoint every
  git call flows through: per-verb subprocess counts and total/avg/max wall-clock since server
  spawn. Read it before and after a heavy act; the delta names the cost. (34th tool.)
- **`imp_flags_all`** — the whole practice's mailroom in ONE crossing: every seat's unread-frontier
  flag, `{seat: {unread, from[]}}`, roster = every perspective (35th tool). A glance surface
  polling per-seat `imp_flags` was paying a linear-in-seats sweep through client rate caps — hot
  by COUNT, the meter's other axis (seat-reported from the 16-seat roster, with numbers).
- **Session binding — the SSH-shaped identity pin** (seat-found: a mis-typed `sender=` landed one
  seat's message on another's branch under the other's name; identity claims were trusted on every
  op by documented design). A connection may now be BOUND to a seat via transport — env per server
  definition (`STASIMA_INSTANCE`), never a payload the model authors — with three modes
  (`STASIMA_BINDING`): **strict** (a mismatched identity-claiming write refuses; the fix is
  out-of-band — that seat's own connection, or witness mode; deliberately no in-call override),
  **witness** (the write proceeds and the mismatch is stamped into the envelope as
  `authored_via=<bound seat>` plus an audit row — nothing blocked, nothing silent), **off**/unset
  (the open trust this deployment ran on, unchanged). Reads are never guarded (pull model,
  world-readable corpus); the relay verbs are outside the guard BY SHAPE (they carry no identity
  parameter — `approved_by` is proven by the TOTP code, not claimed). **Sticky learning is the
  DEFAULT** (port-security with sticky MACs, the practitioner's frame): an unbound connection
  learns its identity from its FIRST identity-claiming write and holds it for the process's life —
  secure by doing nothing; `STASIMA_PORT=<any-unique-token>` makes the learned binding DURABLE
  (persisted as append-only `port_binding` events — the audit ledger IS the running config), and
  `stasima-admin binding` is the console (list the learned table; `--clear <port>` re-arms
  learning, with the rotation history retained by construction). `off` is the explicit,
  server-owned rip-cord — the HTTPS→HTTP downgrade, never callable from the wire. Every binding
  event (pinned spawn, sticky learn, port restore, clear) declares itself into the audit log.
  `whoami` always returns the connection's binding block — mode, bound name, source
  (pinned / port / session), match — so the downgrade is as visible as http:// in an address bar.

### Changed
- **`imp_flags` counts the frontier** — a message superseded by its own sender's later message
  stops flagging (its successor flags instead, if unread); `imp_check` keeps the flat view with
  tombstones. The flag answers "what waits," not "what exists" — and it now agrees with
  `imp_flags_all` on every seat.
- **`imp_send` gains `instance_id=`** as its canonical identity parameter — the same field every
  other op uses; `sender=` stays accepted as the deprecated 0.1.x twin (pass exactly one). The
  forgery-by-typo was invited by `imp_send` being the ONE op with a differently-named identity
  field; uniformity removes the catch-point (root-cause analysis: the finding seat's).

### Changed (performance)
- **Blob reads ride a persistent `git cat-file --batch` sidecar** — one spawn serves every read
  (~2.4 ms vs ~41 ms one-shot; a 40-read sweep dropped 1664 ms → 97 ms, 17×). Refs resolve per
  request, so cross-process updates stay visible; any protocol irregularity retires the sidecar
  and falls back to the one-shot path — never worse than before.
- **`commit_count` is oid-cached** — counts are immutable facts, so the cache can only miss, never
  stale; each commit primes its child from the CAS parent. Removes the write path's one
  O(history) walk (every write previously re-counted its whole trail).
- **Lands index incrementally** (`index_land`) — O(change) instead of a full O(corpus) rebuild
  (~90 s and growing) at every gate stamp; positions provably identical to a full reindex
  (witnessed by running both). `reindex_from_git` remains the recovery/migration path.
- `read_blob`'s ref-existence pre-check moved to the miss path — it taxed every hit with a spawn
  (the meter's first conviction, caught inside the sidecar's own benchmark).
- **Ref resolution rides a short-TTL in-process memo** — a burst resolves the same handful of refs
  over and over (the meter's second field conviction: 6 rev-parse spawns / 345 ms = 56% of an
  arrival burst's boundary time); now the first resolve spawns and the rest hit the memo, ledgered
  as `rev-parse(memo)` — visible, and visibly not a crossing. Own writes refresh their entry in
  place, a CAS failure drops it so the error and any retry read the live tip, and fetch clears it
  wholesale; cross-process movement becomes visible within 3 s, which can only delay a read's view
  — write correctness stays with git's own compare-and-swap, exactly as before.

### Hardening (the post-audit pass)

A seven-dimension adversarially-verified audit of the new HTTP/OAuth foundation (33 confirmed
findings → 14 items) closed the era's buildout. Nothing in this pass changes wire shapes or the
loopback/tailnet trial deployment; the security gates arm only when `http_public_url` turns the
OAuth door on.

#### Security (arms with the OAuth door)
- **TOTP brute-force is closed** — the `/approve` gate had no throttle, so open DCR + unlimited
  6-digit guesses (3-in-10⁶) meant a practitioner-token takeover on public exposure. Now defended
  on both axes: a per-txn burn (a pending approval closes after 5 wrong codes) and a per-IP
  sliding-window rate limiter.
- **A hardening middleware** (`http_guard`) wraps the whole app when auth is on: a Host allowlist
  over the *entire* credential channel (the SDK guard covered only `/mcp`), a request-body cap, the
  per-IP rate limits, and security headers (CSP/nosniff/no-referrer/HSTS/frame-deny) on every
  response. Dynamic client registration is capped (prunes token-less clients before rejecting).
- The approve page now shows the exact `redirect_uri` the code will be sent to (a confused-deputy
  check), `http_public_url` is validated (https unless loopback, http-transport-only, host
  auto-added to the allowlist), and the TOTP secret + `auth.sqlite` are chmod-0600.

#### Performance / lifecycle (foundation, funnel-independent)
- **The audit log is indexed** — every canon-cursor read (per write), read-receipt check (per
  message in the roster sweep), and op-scoped query used to full-scan a never-pruned table; two
  covering indexes + an O(1) PK-tail next-seq + an `audit.latest()` tail lookup retire five
  findings at once.
- OAuth tables are garbage-collected (expired codes/tokens/consumed txns were checked but never
  pruned); the in-memory count/ref caches are size-capped; the map-index write lock no longer spans
  the embedder round-trip; the roster sweep deserializes only each seat's own messages.

#### Correctness
- A log slug differing from its seq only by case (or a trailing-slash domain) is now refused at
  propose instead of failing at the practitioner's land; the cat-file sidecar retires under its
  lock (only the faulted child) and is reaped; `merge-tree` is pinned to resolved oids so an
  out-of-process land can't desync the preview basis; `sup_reconcile`/`propose_retract` emit the
  same audit-error rows the other writers do.

### Suite
- The Aous always-on layer (SKILL.md) compresses its disposition teaching to a pointer index
  (~14% off every conversation's always-on tokens); the docks stay dense. The compression lives in
  the generator, so it rides every future river.

## 0.1.4 — 2026-07-11

**Versioning note.** 0.1.3 never went final: its release candidate (0.1.3a1) soaked in production,
the soak worked — and what the soak's findings built grew past the RC's contents. Cutting that tree
as "0.1.3" would have claimed the RC's blessing for code the RC never contained, so 0.1.3 remains
the version that only ever existed as its candidate, and this line carries everything forward.
Every 0.1.3 breaking shape is unchanged; everything below is additive or a fix.

**The 0.x reset, executed with this release:** 1.0.0–1.0.2 are yanked on PyPI (PEP 592 — pip skips
yanked versions, so `pip install stasima` lands 0.1.4). The historical code remains available in
git history under its true commits; no renumbered republish is performed — the reset is documented
here rather than re-enacted on the index.

### Added (all soak-earned, all seat-reported)
- **`tick=` — the mirror field** (two-clock conventions v3, chorus-reviewed): a state update may
  carry its declared label machine-readably; optional forever, prose governs, hex form and state/
  scope guarded, the value never validated against prose or history; surfaced via `sup_state.ticks`
  and listing pointers (absence is normal and produces no key).
- **`thread=` — the reserved associative tag** on all three carriers (`kip_commit`, `propose` — a
  thread on the log entry tags the whole land — and `imp_send`, so message chains join their work);
  ref-safe form guarded, value semantics deliberately unruled (reserve-the-field-rule-the-values).
- **`thread_scry`** — hinge-free bearings on declared threads: registry (tag, count, authors,
  latest) and per-tag pointers, newest-first, bounded.
- **`arg_scry` — the argot dictionary**, built as the search-aperture's within-practice bore:
  registry of coined terms (distinct-definition count, trees, canon presence) and echo-collapsed
  per-term definitions with every holder annotated; concordance and divergence render as what they
  are; the leash parameter arrives additively when federation's rails exist.
- **The cross-propose attribution guard** — carrying another seat's work toward canon requires
  `origin_author=`; silent reattribution refused on both axes (path under another name; verbatim
  body anywhere — exact match only); the envelope keeps the true author, reindex prefers it over
  the introducer heuristic, `conflict_preview.attributions` shows authored-vs-proposed at the gate.
  Also closes the proposer→confirmed-vantage dignity leak.
- **`map_search` relevance floor machinery** — below-floor hits withheld WITH a count
  (`below_floor`; an empty result is never silent), `include_weak=true` opt-in; the floor is
  embedder-calibrated and config-overridable (`search_score_floor`) — and OFF for the stub
  embedder, whose measured junk/true score ranges overlap.
- **Richer read returns** — `sup_reconcile`'s dedup names its referent (path + oid + subject);
  `kip_history` versions carry titles (the pointer grammar extends to trails).

### Changed
- **Orientation slots join the supersession grammar** — the slot read live-resolves tombstones, so
  a deployment revises its own front door by the ordinary v2+flip land (previously slots could be
  authored once and never lawfully changed).
- **`propose_retract` restores zero divergence** — a canon-held path reverts to canon's current
  edition instead of deleting (a retract can no longer construct a canon-deletion); proposal-added
  paths still leave the tree.
- **`meta/log` proposals fail fast** — missing/non-hex `seq` or slug≠seq refuses at propose-time
  with the fix in the error text, instead of failing at the practitioner's land.
- **The land validator reads the merge candidate** — the same tree `conflict_preview` reads, so the
  two checks can never disagree; a mid-review land no longer makes canon's own newer log read as an
  innocent proposal's second log.

### Fixed
- Path-filtered `list_entries` returned subtree-relative names — blank pointer fields and unusable
  coordinates; `list_paths` now returns full paths under a filter.

## 0.1.3 — never released (superseded in soak by 0.1.4)

**Versioning note.** This release executes the 0.x reset: 1.0.0–1.0.2 are yanked on PyPI and
republished as 0.1.0–0.1.2 (PEP 592 — pip installs the highest non-yanked version, so no rename is
needed). 0.1.3 is the next real release; the version numbers now say what the project is: early,
honest, moving. A stable line starts at 1.1 when it is earned.

### Added
- **The atomic fold** — `kip_commit(horizon=, horizon_title=)` authors an entry and its `confirmed`
  vantage in one commit under one op_id; both fail together, omission stays honest, op_id reuse
  against a recorded vantage is refused, replays are marked (`replayed`) and never index phantom
  content. `vap_record` remains for `reconstructed` and later self-vantages.
- **Live-resolving reads** — `kip_get` follows `superseded_by` to the living edition by default
  (`resolved_from` shows the redirect); `resolve="exact"` deliberately reads a retired edition;
  a missing `.md` is normalized; a miss names the ref(s) where the path actually lives.
- **The combined read** — `kip_get(with_vantages=true)` returns the entry plus its bound vantages
  in full (opt-in; the universal-search exclusion of vantages is untouched).
- **`vap_for` pointer projections** — attributed pointers with preview-240 and the bound entry's
  status by default; `detail="full"` for complete horizons; newest-first; bounded (default 16, the
  hex-page unit) with `offset` paging; per-ref depth ordering for author threads, global recency
  for cross-ref projections. The compaction-recovery convention is stated in the tool itself.
- **Live-only search** — `map_search` excludes superseded editions by default;
  `include_superseded=true` is the deliberate opt-in; every hit carries `status`.
- **Inbox supersession (sender-declared)** — `imp_send(supersedes=)` marks a sender's own earlier
  message replaced; `imp_check` resolves declared edges across the whole inbox and returns
  flat-with-tombstones (`superseded_by` on each superseded message). Author-scoped: no sender can
  tombstone another sender's message.
- **The mechanical two-clock pin** — every write stamps `canon_state` (the author's reconcile
  cursor) and `instance_depth` (the target ref's commit position) into the envelope; reindex-proof
  by construction. Canon rows derive their positions from canon's own first-parent history at
  reindex — envelope pins are authoring coordinates; index positions are the row's own clock.
- **Enriched listings** — `list_entries` and `my_perspective` return triageable pointers
  ({path, title, status, type}) from a single index query.
- **Pointer `canon_diff`** — path/title/type/status per changed entry plus each land's log
  narrative in full; bodies never ride, so a large land cannot overflow the reconcile hinge.
- **`git_network_timeout`** — network/batch git ops (backup, mirror, sync) get a generous
  configurable bound (default 300 s) decoupled from the interactive hang-guard.
- **Generated tool reference** — `docs/tools.md`, derived from the live registry by
  `docs/gen_tools.py`; kept alive by a suite test.

### Changed — BREAKING (see docs/upgrading.md for the cutover)
- `kip_get` returns a dict (`text`/`path`/`status`/`title`[/`resolved_from`/`vantages`]) instead of
  a bare string.
- `canon_diff` returns pointers + log narratives (`changed`/`changed_count`/`logs`) instead of full
  entry bodies (`content`).
- `list_entries` / `my_perspective` return objects per entry instead of bare path strings.
- `vap_for` returns pointers by default instead of full horizons (opt back in with
  `detail="full"`); response gains `count`/`total`/`truncated`/`offset`.
- `map_search` hits gain `status`; results exclude superseded editions by default.

### Fixed
- Backups aborting at the 2 s interactive git timeout (the release's motivating bug).
- The write-path CAS cluster: guards and pins were computed against a pre-retry tip (stale
  `instance_depth`, an immutability-guard bypass window); the content builder now re-runs all
  per-tip work against the exact CAS parent per attempt.
- Replayed ops indexing content git never received (the phantom-vantage class).
- A fresh perspective's first commit pinning canon's depth instead of 1.
- `vap_for` `binds_status` blank for reconstructed/canon-bound vantages; per-ref depth used as a
  cross-author sort key (a verbose author buried newer vantages).
- Cross-sender inbox tombstone spoofing (supersedes edges are author-scoped).
- Proposal-branch positions leaking into canon's index as if they were canon positions.

### Suite (deployment-side, landed in the Rehearsal canon)
- **Atrax** — the third river: canon-sourced dispositions (five stances, both failure directions
  named) and six canon-sourced docks; skills regenerate from canon (::D).
- Canon's first supersession: the recover/author/message docks revised in place for the 0.1.3
  layer (::E); tombstone resolution verified live.
- Test suite 19 → 21 (witnessing tests for replay, phantom, reuse, spoof, ordering, positions,
  the network timeout, and the doc generator).

## 0.1.0 – 0.1.2 (republications of 1.0.0 – 1.0.2)
- **0.1.2 (as 1.0.2)** — VAP: the vantage organ (`vap_record`/`vap_for`), dignity guard,
  server-pinned canon-state. 30 tools.
- **0.1.1 (as 1.0.1)** — the multi-instance hardening harvest (stdio robustness, append-only canon
  guard, name-fork guard, list-fusion fix), the Strophos participant skill, `admin mirror`, the
  beta cockpit TUI.
- **0.1.0 (as 1.0.0)** — the local stack: git-backed CAP store, MAP index, hash-chained audit log,
  the human gate, the TOTP airlock, HTTP transport, the admin CLI. Published via Trusted Publishing.
