# Stasima — Operations (day-to-day)

The keep-open doc. Once you're set up ([SETUP.md](SETUP.md)), this is everything you need to run and tend a deployment. Run the server with:

```bash
STASIMA_CONFIG=/abs/path/to/stasima.toml stasima
```

**Two transports** (`transport` in the config):
- **`stdio`** (default) — each MCP client spawns the server as its own subprocess. Simplest; on-box only; right for a single client at a time.
- **`http`** — *one* continuously-running server; every instance connects to `http://<host>:<port>/mcp`. Right for "the server lives on this machine and runs all the time," and required once multiple instances connect concurrently (a single process must own the audit chain). Claude Code: `claude mcp add --transport http stasima http://127.0.0.1:8787/mcp`. To keep it running on Windows, register the command as a logon task in Task Scheduler (or wrap it as a service with NSSM).

**Reaching it from your other devices — Tailscale.** Until transport auth lands (1.1), the config *refuses* to bind beyond loopback or a Tailscale 100.x address — nothing can listen toward the open internet, by validation rather than by discipline. With the server on loopback, run `tailscale serve --bg 8787` on the server machine: your other tailnet devices connect via the HTTPS URL it prints, tailnet membership is the auth, and the open internet still sees nothing. One config line makes the proxy's hostname acceptable to the server's DNS-rebinding protection (on by default; it rejects unfamiliar `Host` headers): `http_allowed_hosts = ["yourbox.your-tailnet.ts.net"]`. Binding your `100.x` address directly needs no extra line — the allowlist follows the bind. (Public exposure — needed for claude.ai web/mobile connectors — is a 1.1-era decision, alongside per-instance tokens.)

All maintenance is through the admin CLI, which you point at the same config:

```bash
stasima-admin --config stasima.toml <command>
```

---

## Your job: review and land proposals

This is the part only you can do. An instance creates a proposal (`propose`); it sits as a branch until you decide. The loop:

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

**The flow** (you speak the codes; the instance relays them to `stage_approve` / `land_approve`):
1. Give the instance your **current code** → it stages the proposal: frozen for review, merge prepared, and you're shown the staged oid, changed paths, and log-entry seq.
2. **Review** — at least 2 minutes, at most 2 hours (configurable). No code from staging time survives this window, so a harvested code can't land.
3. Give a **fresh code** (a later window) plus the staged oid prefix → it lands exactly what was staged: the full land chain runs (audit, state tag, reindex, anchor).
4. **To decline: just say so** — `stage_revert` needs no code, ever. Expired stages auto-revert.

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

- **An instance says it can't propose ("reconcile with current canon first").** Working as intended — canon advanced since it last reconciled. It must call `canon_diff` then `sup_reconcile`, then it can propose. You don't need to do anything.
- **`land` refuses: missing log entry, or wrong seq.** Also working as intended. Missing → the instance authors one (`propose` with `domain='meta/log'`, the expected seq from `preview`). Wrong seq → another proposal landed first; the instance re-reconciles, retracts the stale log entry (`propose_retract`), and re-authors it at the new seq.
- **Search returns nothing / stale results.** `reindex`. (Also do this after changing the embedding model.)
- **Lost or corrupted `map_index.sqlite`.** Delete it and `reindex` — it's a cache.
- **`verify` reports a bad seq, or audit-vs-anchor is false.** The `audit.sqlite` was altered or corrupted out of band. Restore it from backup; the git-anchored head tells you the last known-good checkpoint.
- **A committed op has no audit entry** (e.g., the server died mid-write). `reconcile` backfills it from git.
- **Server won't start.** Check the config: `git_dir` must point at the bare repo; if `embed_backend = "local-server"`, `embed_url` is required. Config errors print a specific message.
- **Something feels slow.** `perf_scry` (any connected instance can call it) is the server-git
  boundary's complete ledger since the server spawned: per-git-verb call counts and total/avg/max
  wall-clock. Read it before and after the slow act — the delta names the cost. A verb hot by
  COUNT wants batching; hot by MAX wants an algorithmic look. (Blob reads ride a persistent
  `cat-file` sidecar and self-heal to one-shot calls on any irregularity — a slow read path is
  therefore worth reporting, not expected. Ref resolution rides a short-TTL in-process memo:
  `rev-parse(memo)` rows in the ledger are hits, not subprocess crossings — a healthy burst shows
  few `rev-parse` spawns and many memo hits.)

## Seat identity and session binding (the SSH shape)

Identity in Stasima is TOFU, deliberately — and the binding layer manages it the way SSH does,
with three postures per connection:

- **Pinned** (recommended for archive seats and any seat you never act-as-others through): set
  `STASIMA_INSTANCE=<seat>` in that server definition's env. Trust comes from a config entry you
  authored — `known_hosts` pre-seeded — so there is no first-use moment at all.
- **Open** (any definition with no `STASIMA_INSTANCE`): identity claims are trusted per call, the
  deployment's original behavior. Right for a single-human deployment's general-purpose console.
- (Accept-new-and-hold — classic TOFU, binding at `announce` — is the designed shape for the HTTP
  transport, where real per-session headers exist. Not built; the design is on record.)

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

**Rekeying.** Today: edit the env, restart that server — every bound spawn writes a
`session_binding` row into the audit log, so rotations leave a readable trail. When the binding
table moves server-side (the HTTP/announce-time era), console verbs (`binding list/set/clear`)
take over and the same trail continues. The relay path needs no exemption at any point: the
approval verbs carry no identity parameter — `approved_by` is proven by the TOTP code, never
claimed by the session.

---

## Scope: v1 and what's deferred

**v1 is** a single-practitioner, local-first, fully-tested stack — one process, git + two SQLite files, on your machine.

**Deferred to later versions** (none block using v1; all additive):
- **GitHub / multi-machine sync**, and **multi-user with cryptographic identity** — v1 is single-practitioner, names-as-identity.
- **The richer messaging social layer** (tiers, subscriptions, message expiry) and an agentic **Cartographer** that reads across perspectives.

For the full picture of what's built and deferred, see `stasima-v1-build-state.md` in the parent folder.
