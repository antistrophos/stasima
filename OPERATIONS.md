# Stasima — Operations (day-to-day)

The keep-open doc. Once you're set up ([SETUP.md](SETUP.md)), this is everything you need to run and tend a deployment. Run the server with:

```bash
STASIMA_CONFIG=/abs/path/to/stasima.toml stasima
```

**Two transports** (`transport` in the config):
- **`stdio`** (default) — each MCP client spawns the server as its own subprocess. Simplest; on-box only; right for a single client at a time.
- **`http`** — *one* continuously-running server; every instance connects to `http://<host>:<port>/mcp`. Right for "the server lives on this machine and runs all the time," and required once multiple instances connect concurrently (a single process must own the audit chain). Claude Code: `claude mcp add --transport http stasima http://127.0.0.1:8787/mcp`. To keep it running on Windows, register the command as a logon task in Task Scheduler (or wrap it as a service with NSSM).

**Reaching it from your other devices — Tailscale.** The config *refuses* to bind beyond loopback or a Tailscale 100.x address — nothing can listen toward the open internet, by validation rather than by discipline. Transport auth exists (the OAuth door, `http_public_url` — below); the restricted bind stays as defense-in-depth behind it. With the server on loopback, run `tailscale serve --bg 8787` on the server machine: your other tailnet devices connect via the HTTPS URL it prints, tailnet membership is the auth, and the open internet still sees nothing. One config line makes the proxy's hostname acceptable to the server's DNS-rebinding protection (on by default; it rejects unfamiliar `Host` headers): `http_allowed_hosts = ["yourbox.your-tailnet.ts.net"]`. Binding your `100.x` address directly needs no extra line — the allowlist follows the bind. (Public exposure — needed for claude.ai web/mobile connectors — is now a policy decision, not a missing gate: the OAuth door + the hardening middleware are built and tested; per-seat tokens remain the follow-on.)

All maintenance is through the admin CLI, which you point at the same config:

```bash
stasima-admin --config stasima.toml <command>
```

---

## Your job: review and land proposals

This is the part only you can do. A seat creates a proposal (`proposal_append_entry`); it sits as a branch until you decide. The loop:

```bash
stasima-admin --config stasima.toml status        # what's open
stasima-admin --config stasima.toml preview p-1   # dry-run: conflicts? what paths change?
stasima-admin --config stasima.toml land p-1 --by practitioner
```

`land` is the human gate. It merges the proposal into canon, records it in the audit log, **tags the merge commit with the new state number** (`state/<seq>`), rebuilds the search index, and writes a tamper-evident checkpoint of the audit chain into git. After a land, every instance must reconcile with the new canon before its next proposal — that's by design (it keeps them current with shared truth).

**Every proposal must carry exactly one log entry** (`meta/log/<seq>.md`) — the authored narrative of what the change is and why it matters. `preview` shows whether it's present (`log_entry_ok`) and what seq is expected; `land` refuses without it, and refuses a seq that isn't canon's + 1. Read the log entry as part of your review — it's the story that lands with the work, and canon's state number (`::3C`, `::3D`, …) advances with each land, continuing the chat-era sequence from `::3B`.

If `preview` reports conflicts, don't land — the proposing instance needs to reconcile and re-propose against current canon.

### The menu cockpit (beta)

Don't want to keep commands handy? `stasima-cockpit --config stasima.toml` (or set `STASIMA_CONFIG` and run it bare) opens a menu over these same operations — a live status header (canon seq, audit health), a proposals list you pick from, an inline `preview`, and a land that asks you to **type the proposal id** to confirm. It's the **console channel** — you're at the terminal, so there's no TOTP; your presence is the gate — and it drives the exact same `run()` the CLI does, so it refuses whatever the CLI refuses (a conflict, an append-only removal, a missing log entry). Being beta, it has rough edges: it lists already-landed proposals too (they preview as "no changes — already in canon," and it won't offer to land them), and remote/airlock approval isn't in the menu yet — use the CLI airlock flow below for that.

## Approving remotely (the airlock)

When you're not at the console and approving *through an instance conversation* (e.g. on your phone), use the airlock instead: two TOTP codes from your authenticator app, one per phase, with enforced review time between them. The console `land` path is unchanged — at the console, the console is your out-of-band channel.

**One-time setup:** `stasima-admin --config stasima.toml totp-provision` — add the printed `otpauth://` URI to your authenticator app (every major app also accepts the `secret=` value via "enter a setup key", time-based, 6 digits). The secret stays server-side (never in git; it's gitignored). Then confirm the pairing with a code from your phone: `stasima-admin … totp-check 123456` — it verifies without consuming anything and diagnoses clock skew if the code doesn't match.

**The flow** (you speak the codes; the instance relays them to `proposal_stage` / `proposal_land`):
1. Give the instance your **current code** → it stages the proposal: frozen for review, merge prepared, and you're shown the staged oid, changed paths, and log-entry seq.
2. **Review** — at least 2 minutes, at most 2 hours (configurable). No code from staging time survives this window, so a harvested code can't land.
3. Give a **fresh code** (a later window) plus the staged oid prefix → it lands exactly what was staged: the full land chain runs (audit, state tag, reindex, anchor).
4. **To decline: just say so** — `proposal_unstage` needs no code, ever. Expired stages auto-revert.

Trust note: what the relaying instance *shows* you is its own rendering. Content-binding guarantees what lands is byte-identical to what was staged, and the audit trail records everything — but for anything you're unsure about, the console (`preview`) is the stronger channel.

Troubleshooting the gates (each error names the failed gate and both values): "review floor not met" — wait, then send a *fresh* code. "not strictly later" / "consume-once" — the code was already seen; wait ~30s for the next one. "content-binding" — the oid prefix doesn't match what's staged; re-check with the staged oid from staging (or `admin status`). "frozen for review" — an instance tried to modify a staged proposal; land or revert first.

---

## Admin CLI reference

| command | what it does |
|---|---|
| `status` | canon head, perspectives, open proposals, audit health |
| `preview <id>` | dry-run a proposal merge (conflicts / changed paths) — review before landing |
| `land <id> [--by NAME]` | **approve + land** a proposal to canon (the human gate) |
| `reindex` | rebuild the search index from git (after a model swap, or to recover it) |
| `reconcile` | backfill audit entries for any committed op missing one (crash recovery) |
| `verify` | check the audit chain's integrity, and the git-anchored checkpoint |
| `anchor` | write the current audit head into git now |
| `bootstrap <dir>` | *(one-time, setup only)* seed an empty canon from a folder of entries |
| `inbox [--all] [--read PATH]` | your mail, from the cockpit — unread by default; `--read` marks handled |
| `totp-provision [--qr] [--force]` | generate (or re-display / rotate) the airlock secret |
| `totp-check <code>` | verify a phone code; consumes nothing, diagnoses clock skew |
| `backup <dest>` | full **local** backup: git mirror (all refs + state tags, verified), consistent audit snapshot, config, TOTP secret. For a same-trust machine move |
| `mirror <url>` | off-machine backup to a git **remote** (e.g. a private repo): content refs + audit snapshot on `refs/backup/audit`, verified. **No secret pushed.** Run on a cadence |

---

## Updating canon & the orientation slots

Canon is never edited directly — the same gate applies to you. To change a canon entry (including an orientation slot like `technical/orientation/conduct.md`), it goes through a proposal you then land. In practice you'll usually have an instance draft the change and propose it; you `preview` and `land`. To author entirely on your own, you can run an instance yourself, or draft the entry and have any instance propose it.

Remember **supersede, not edit**: a revised entry is a *new* entry that supersedes the old (the old stays, marked superseded, so existing references still resolve).

---

## Staying reachable (interim)

Out-of-band notification isn't built yet (a 1.x item), so an instance's messages to you — including an "I think I'm drifting" call — wait in a pull inbox until you look. Until notification exists, **you have to poll**, and the cockpit covers it: `stasima-admin … inbox` lists your unread mail (sender, authored subject, coordinates), `inbox --read <path>` marks one handled, and `status` shows the unread count (`practitioner_unread`) so a routine status check doubles as the mail check. Make the cadence an explicit commitment in your deployment's `conduct/` corpus ("the practitioner checks at least every N") — that turns an unstated gap into a kept promise, and it's corpus-level, not protocol.

---

## Backups & what's truth

- **The method is one command:**
  ```bash
  stasima-admin --config stasima.toml backup /path/to/destination
  ```
  It captures everything that is truth, correctly, every time: a full-ref git mirror (heads + perspectives + proposals + **state tags**, verified after push), a consistent snapshot of `audit.sqlite` (safe against a live server), your config, and the TOTP secret. Repeatable and incremental — point it at a synced folder, an external drive, or a network share, on a cadence.
- **If you push the git repo to a remote by hand** (e.g. a private mirror), you must name all three namespaces — git's defaults silently drop two of them, and a partial refspec silently drops the state tags:
  ```bash
  git -C stasima.git push <remote> 'refs/heads/*:refs/heads/*' 'refs/cap/*:refs/cap/*' 'refs/tags/state/*:refs/tags/state/*'
  ```
  This is exactly the mistake `backup` exists to make impossible — prefer the command.
- **Off-machine, on a cadence:** `mirror <url>` pushes content + a consistent audit snapshot to a git remote — ideally a **private** repo, separate from the public suite repo (your canon is never the suite's concern). One command, verified, the TOTP secret deliberately excluded (it's the airlock key; re-provision on restore). This is the "doesn't live and die with one machine" answer; `backup` is the local-bundle / same-trust-move answer.
- **The live deployment is single-writer, local-disk.** The two truths (`git_dir`, `audit.sqlite`) belong on the server machine's plain local disk — **not** a cloud-synced folder (a sync client copying git/sqlite mid-write corrupts them) and **not** inside the suite clone. Other devices are *clients* (over the tailnet), never second writers. `mirror`/`backup` snapshots are sync-safe; the live copy is not.
- **`map_index.sqlite` needs no backup** — `reindex` regenerates it from git.
- **Verify integrity** anytime with `verify`. The audit chain is hash-linked, and the per-land git checkpoint lets git witness any tampering of the SQLite log.
- **Moving machines:** run `backup`, carry the destination folder + the suite code; on the new box `pip install mcp`, point the config at the mirrored repo (or clone from it), `reindex`, run. The backup includes the TOTP secret, so the airlock pairing moves with you.

---

## Embeddings

Search quality depends on this. `embed_backend = "stub"` is offline and deterministic but only lexical-ish. For real semantic search, run a local model server and set in `stasima.toml`:

```toml
embed_backend = "local-server"
embed_url     = "http://localhost:11434"  # Ollama; LM Studio is usually :1234
embed_model   = "nomic-embed-text"
embed_dim     = 768
embed_doc_prefix   = "search_document: "  # nomic-style models REQUIRE task prefixes —
embed_query_prefix = "search_query: "     # without them, ranking is worse than the stub
```
Then `reindex` once to re-embed the corpus. Swapping models is always a clean rebuild (the model id is tagged per row) — check the new model's prefix convention when you swap (set both prefixes to `""` for models that don't use them). `embeddings_smoke.py` verifies a live server end to end (semantic ranking on a word-disjoint query).

---

## Troubleshooting

- **An instance says it can't propose ("reconcile with current canon first").** Working as intended — canon advanced since it last reconciled. It must call `canon_diff` then `canon_reconcile`, then it can propose. You don't need to do anything.
- **`land` refuses: missing log entry, or wrong seq.** Also working as intended. Missing → the instance authors one (`proposal_append_entry` with `domain='meta/log'`, the expected seq from `preview`). Wrong seq → another proposal landed first; the instance re-reconciles, retracts the stale log entry (`proposal_retract_path`), and re-authors it at the new seq.
- **Search returns nothing / stale results.** `reindex`. (Also do this after changing the embedding model.)
- **Lost or corrupted `map_index.sqlite`.** Delete it and `reindex` — it's a cache.
- **`verify` reports a bad seq, or audit-vs-anchor is false.** The `audit.sqlite` was altered or corrupted out of band. Restore it from backup; the git-anchored head tells you the last known-good checkpoint.
- **A committed op has no audit entry** (e.g., the server died mid-write). `reconcile` backfills it from git.
- **Server won't start.** Check the config: `git_dir` must point at the bare repo; if `embed_backend = "local-server"`, `embed_url` is required. Config errors print a specific message.
- **Something feels slow.** `server_stats` (any connected instance can call it) is the server-git
  boundary's complete ledger since the server spawned: per-git-verb call counts and total/avg/max
  wall-clock. Read it before and after the slow act — the delta names the cost. A verb hot by
  COUNT wants batching; hot by MAX wants an algorithmic look. (Blob reads ride a persistent
  `cat-file` sidecar and self-heal to one-shot calls on any irregularity — a slow read path is
  therefore worth reporting, not expected. Ref resolution rides a short-TTL in-process memo:
  `rev-parse(memo)` rows in the ledger are hits, not subprocess crossings — a healthy burst shows
  few `rev-parse` spawns and many memo hits.)

## Seat identity and binding (the SSH shape)

Identity in Stasima is TOFU, deliberately — and the binding layer manages it the way SSH does,
with three postures per server process (binding lives at **process grain**: the MCP protocol since
2026-07-28 has no per-conversation session for anything to bind to — see the trunk caveat below):

- **Pinned** (archive seats, and any seat you never act-as-others through): set
  `STASIMA_INSTANCE=<seat>` in that server definition's env. Trust comes from a config entry you
  authored — `known_hosts` pre-seeded — so there is no first-use moment at all.
- **Sticky — the DEFAULT, nothing to set** (port-security with sticky MACs): an unbound connection
  learns its identity from the FIRST identity-claiming write and holds it for the life of the
  process. Add `STASIMA_PORT=<any-unique-token>` to a definition and the learned binding becomes
  DURABLE — persisted as append-only `port_binding` events in the audit log (the ledger is the
  running config), restored at every respawn, cleared only from the console. The token is a
  meaningless unique string, not an identity decision.
- **Off** (`STASIMA_BINDING=off`, explicit): the rip-cord — no learning, no enforcement, the
  HTTPS→HTTP downgrade. Deliberately server-owned: it exists only in env/console, never as
  anything a caller could request. `seat_whoami` shows the downgrade plainly, like http:// in the
  address bar.

**The trunk caveat (field-found, 2026-07-18).** Some clients share ONE server process across many
chats — the Claude desktop app does. A shared definition there is a TRUNK, and sticky on a trunk
means first-chat-wins: the first seat to write binds the process and every other seat's writes
refuse (strict) or mis-stamp (witness — the `authored_via` would name the wrong chat, so witness
is dishonest on a shared process). Rule: **shared definitions run `off`; binding belongs on
per-seat pinned definitions** (each enabled only in its seat's chat — the definition is the access
port). The HTTP fleet service is a shared process by nature, and the protocol gives it nothing
finer to bind: MCP 2026-07-28 removed protocol sessions (even a handshake-era client is handed a
fresh session object per request). So the service runs `off` — attribution still rides every
write, and every audit row from the http transport carries a `session` label (a legacy client's
transport-session id, or `stateless`) so cross-conversation forensics stays a query — or it is
**pinned** to one seat and becomes that seat's own door. The server **refuses to start** an http
service that could learn (`strict`/`witness` with no `STASIMA_INSTANCE`): a shared service that
learned would bind the whole fleet to its first writer. Never sticky a trunk.
- Per-request identity for a shared service is the **token door** (the OAuth layer, below): the
  seat's credential rides each request, and adoption mints the credential together with the name.
  That is the designed shape; the binding modes above are the process-grain guard until it lands.

`STASIMA_BINDING` picks what a bound connection does on a MISMATCHED identity-claiming write
(reads are never guarded; the corpus is world-readable and the inbox is pull):

- **strict** (default when an instance is set): the write refuses, and the error names the fix.
  The override is a **config edit on your side** — use the seat's own definition, or flip this one
  to witness — never an in-call parameter and never a relayed code (an in-band override would be
  one more trusted assertion; making codes routine would erode never-solicit).
- **witness**: the write proceeds and confesses — the envelope carries `authored_via=<bound seat>`
  into git permanently, and the audit log records the mismatch. Use this wherever you legitimately
  act as more than one name through one connection: nothing is blocked, and the record cannot
  silently misattribute.

## Running the HTTP service (the fleet server)

One long-running process serves every seat, and one meter/memo/sidecar warms for the whole fleet.
It is a shared process, so it runs with binding `off` (or pinned to one seat) — see "Seat identity".

**Config — a SEPARATE toml for the service.** Do not flip the shared stdio toml to
`transport = "http"`: stdio definitions spawn children that read the same file and would each try
to serve HTTP. Copy it (e.g. `stasima-http.toml`), same `git_dir` and derived DB paths, plus:

    transport = "http"
    http_port = 8787          # bind stays loopback/tailnet (defense-in-depth); auth is the OAuth
                              # door (http_public_url), not the bind — see "The OAuth door" below

**Start it** (console): set `STASIMA_CONFIG` to the http toml and run `python -m
stasima.cap_server` — the window IS the service; Ctrl+C stops it. To survive logins, put a
one-line `.cmd` (set the env, start the module) in the Startup folder or a Task Scheduler
logon task. Run the fleet service with `binding_mode = "off"` in its toml (the server refuses to
start a shared service that could learn); `STASIMA_INSTANCE` in its env would make the whole
service a single-seat door — legitimate, but only if that is what you mean.

**HTTPS for the desktop connector (the client requires TLS on remote connectors).** Terminate
TLS in front of the loopback service — `tailscale serve --bg 8787` gives a real cert on your
`https://<host>.<tailnet>.ts.net/` with no cert management (tailnet-only; `funnel` = public and
stays off until auth). Add the proxied Host to the http toml or our DNS-rebinding guard 421s it:
`http_allowed_hosts = ["<host>.<tailnet>.ts.net"]`.

**The OAuth door (required once the client dials a remote HTTPS connector).** The desktop client
demands the MCP authorization flow from remote connectors — it will not connect to a bare HTTPS
endpoint. Turn the authorization server ON by setting the public URL in the http toml:

    http_public_url = "https://<host>.<tailnet>.ts.net"

This mounts discovery, dynamic client registration, `/authorize`, `/token`, and a bearer
requirement on `/mcp` — all from the SDK; the provider behind them (`stasima/oauth.py`) stores
clients and tokens in `auth.sqlite` (beside the audit log, in the backup path) and gates approval
with **the same TOTP that gates canon**. Flow, one-time per connector: the client registers
itself, the browser opens the server's approve page, you enter a code from the practitioner's
authenticator, and the connector receives a token (auto-refreshed thereafter, revocable by
clearing `auth.sqlite`). No passwords, no accounts — presence-proof, the airlock's own discipline
(a consumed TOTP window can't approve twice). **The console is the other channel**: cockpit →
HTTP service screen shows waiting approvals (`a` to review, type the client name to confirm) —
presence at the terminal is the gate, exactly like landing, and the browser page follows home on
its own. The cockpit's `u` key writes `http_public_url` + the Host allowance into the http toml
for you. Leave `http_public_url` blank for a loopback-only
service: no auth, the deployment's prior behavior. A bridge client (`mcp-proxy`/`mcp-remote`,
stdio→HTTPS) is the alternative when you'd rather not run the auth server — it presents locally so
no OAuth is demanded, one thin process per chat, one heavy server behind them.

**Connect the client**: desktop Settings → Connectors → add custom connector (the `https://…ts.net/mcp`
URL when TLS+OAuth are on, or `http://127.0.0.1:8787/mcp` for a loopback trial); enable it per
conversation exactly like the stdio definition.
Migration is per-seat and reversible — stdio definitions keep working unchanged throughout
(their spawned children and the service share git via CAS and the SQLite files via file
locking, the same multi-process reality the stdio fleet always had). Rollback = stop the
service; seats reopen on stdio.

**Verify**: `seat_whoami` in any conversation shows the `binding` block (`grain: process`, `mode: off`
on a shared service); audit rows from the http transport carry a `session` label; `server_stats`
becomes the whole fleet's one ledger.

**Stateless http — `http_stateless = true` — and the restart rule it dissolves.** With sessions
(the default), a bridge holds ONE upstream transport session and **does not reconnect if the
service restarts** — the old session goes stale and every seat's next tool call terminates
("Session terminated" / "Server transport closed unexpectedly"). The order was therefore a rule:
restart the service first, THEN fully quit and relaunch the desktop client so it respawns fresh
bridges. `http_stateless = true` serves every request on a fresh transport and assigns no session
at all (the protocol has none since 2026-07-28; this stops offering one to handshake-era clients
too), so an open bridge simply carries on across a service restart. Measured, not assumed:
`bridge_smoke.py` drives the ported server through the real `mcp-proxy` bridge in both modes and
restarts the service under the open bridge — sessions: `survives-restart=NO`; stateless: `YES`.
The cost is one forensic label: audit rows from legacy clients read `session: stateless` instead of
the bridge's session id. Recommended for the fleet. Run the smoke on the deploying machine before
flipping it; keep the old rule for any deployment that stays on sessions.

**Cutover to the v2 service (0.1.5 → 0.2.0) — the sequence.** The SDK upgrade must NOT land in the
interpreter that runs the bridge (`mcp-proxy` declares `mcp>=1.17` with no ceiling and predates the
v2 SDK); the service gets its own venv, and the bridge's interpreter stays exactly as it is.

1. **Build the venv** beside the checkout and install the release into it:
   `python -m venv <dir>\.venv` → `<dir>\.venv\Scripts\python.exe -m pip install stasima==0.2.0`
   (or `-e <checkout>` for a source deployment). Do not touch `pip` in the bridge's interpreter.
2. **Give the new generation its own config pair and launcher** — do NOT add the v2 fields to the
   0.1.5 http toml: the 0.1.5 config loader refuses unknown keys, so the old cockpit's start button
   would fail and the trivial rollback with it. Copy the base toml to `<stem>-v2.toml` and the http
   toml to `<stem>-v2-http.toml` (same `git_dir`, same databases, same port, `binding_mode = "off"`),
   and add to the http copy: `service_python = "<dir>/.venv/Scripts/python.exe"` and
   `http_stateless = true` (after the smoke). Write a `cockpit-v2` launcher that clears `PYTHONPATH`
   (no source path may shadow the venv), sets `STASIMA_CONFIG` to the v2 base toml, and runs
   `<dir>\.venv\Scripts\python.exe -m stasima.tui`. Each cockpit now derives its own http toml and its
   own pidfile, and manages its own service generation; the old files are never edited.
3. **Run the smoke** from the venv: `<dir>\.venv\Scripts\python.exe bridge_smoke.py`. Two rows,
   both `tools=29 announce=OK write=OK`; the stateless row `survives-restart=YES`.
4. **Back up** (`admin backup`), then **stop the old service from the OLD cockpit** (HTTP service →
   `x`) and **start the new one from the NEW cockpit** (HTTP service → `s`; the start line names the
   venv interpreter). Same port, same data, new code.
5. **Bounce the desktop client once** — this is the LAST time the bridge rule applies: the bridges
   were born against the old, session-holding service. From here on a stateless service restarts
   under open bridges.
6. **Verify** in one conversation: `seat_whoami` shows `"grain": "process"`, `"mode": "off"`;
   `canon_state` answers; a deliberate refusal (e.g. a `entry_write` re-using a slug) comes back as
   its own sentence, not "Error executing tool".

**The service log.** Since 0.3.1 the cockpit's `s` writes the service's own output to `<http toml>.log`
beside its config, appended across restarts with a start marker per launch. Read it first when a
call hangs or a seat reports a silence: a handler's traceback and the SDK's request log are there
and nowhere else. It grows slowly (one line per request); prune it when you back up.

**Rollback** needs no data step (git, the audit log, the map index, and `auth.sqlite` are
untouched by any release since 0.1.5): stop the service from its cockpit (`x`), check out the
previous release in the checkout the service venv imports (`git -C <checkout> checkout v0.2.1`),
start it again (`s`), put the previous suite's skill back in every client, bounce the client.
`git checkout main` in that checkout brings the code forward again; nothing is edited in either
direction. The 0.1.5 launcher (`cockpit.cmd`: the shared interpreter with `PYTHONPATH` on the
checkout) cannot start anything on `main` from 0.2.0 on — that interpreter lacks SDK 2.1, so it
exits on import — and is not a rollback path; retire it and its toml pair.

**Binding over the bridge — `binding_mode = "off"`, as for any shared service.** The bridge
multiplexes every conversation onto ONE transport session per bridge process, so even in the era
when binding keyed on transport sessions it would have bound the *bridge* (a trunk), not the
conversation: two seats that share a bridge collide (one binds it, the other's writes refuse).
Today the server refuses to start a shared service that could learn, so the toml carries `off`.
Attribution still rides every write; per-request identity (and its anti-spoofing) returns with the
token door, where each request carries the seat's credential.

**Rekeying.** Per source: a process-sticky binding dies with its process (rekey = close and
reopen the chat); a port-sticky binding is cleared from the console — `stasima-admin binding`
lists the learned table, `stasima-admin binding --clear <port>` appends a clear event and re-arms
learning (the history is never erased — the ledger keeps every learn and clear in order); a
pinned binding is an env edit + restart. The cockpit carries all of it as menu 4 — **Bindings**:
the sticky table, the recent binding events, the env cheat-sheet, and the clear behind the same
type-the-token guard the land stamp uses. Every binding event writes an audit row, so the whole
rotation history is readable at any time. The relay path needs no exemption at any point: the
approval verbs carry no identity parameter — `approved_by` is proven by the TOTP code, never
claimed by the session.

---

## Scope: v1 and what's deferred

**v1 is** a single-practitioner, local-first, fully-tested stack — one process, git + two SQLite files, on your machine.

**Deferred to later versions** (none block using v1; all additive):
- **GitHub / multi-machine sync**, and **multi-user with cryptographic identity** — v1 is single-practitioner, names-as-identity.
- **The richer messaging social layer** (tiers, subscriptions, message expiry) and an agentic **Cartographer** that reads across perspectives.

For the full picture of what's built and deferred, see [STATUS.md](STATUS.md).
