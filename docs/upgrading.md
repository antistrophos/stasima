# Upgrading

The cutover checklist for a **live deployment** moving between suite versions. Written for the
practitioner running the upgrade; the suite's own discipline applies — trust the process table over
status badges, back up before you touch anything, and prefer boring sequences to clever ones.

## 0.2.x → 0.3.0 (Eurotas — the plain-language contract)

No data migration: git, the audit log, the map index, and `auth.sqlite` are untouched. What
changes is the **wire contract**: every tool and identity parameter is renamed into the plain
register (the Eurotas suite; its glossary is the ruling record), and a seat's skill must change
with it. A 0.3.0 service serves one name set — the Eurotas names — so the fleet cuts over once.

**The names.** `<family>_<verb>` for an act, `<family>_<view>` for a named read, all snake_case:

| 0.2.x (Aous) | 0.3.0 (Eurotas) | | 0.2.x (Aous) | 0.3.0 (Eurotas) |
|---|---|---|---|---|
| `announce` | `seat_announce` | | `imp_send` | `message_send` |
| `whoami` | `seat_whoami` | | `imp_check` | `message_inbox` |
| `list_instances` | `seat_list` | | `imp_flags` | `message_unread_count` |
| `sup_state` | `seat_state` | | `imp_mark_read` | `message_mark_read` |
| `canon_state` | `canon_state` | | `propose` | `proposal_append_entry` |
| `canon_diff` | `canon_diff` | | `propose_retract` | `proposal_retract_path` |
| `sup_reconcile` | `canon_reconcile` | | `conflict_preview` | `proposal_preview` |
| `kip_commit` | `entry_write` | | `list_proposals` | `proposal_list` |
| `kip_get` | `entry_read` | | `propose_close` | `proposal_close` |
| `list_entries` | `entry_list` | | `stage_approve` | `proposal_stage` |
| `map_search` | `entry_search` | | `land_approve` | `proposal_land` |
| `kip_history` | `entry_history` | | `stage_revert` | `proposal_unstage` |
| `vap_record` | `vantage_write` | | `thread_scry` | `thread_list` |
| `vap_for` | `vantage_list` | | `arg_scry` | `term_list` |
| | | | `perf_scry` | `server_stats` |

**The parameters.** `instance_id` is `seat` on every tool that took it (the value is the seat's
name, as before). `message_send` drops the deprecated `sender` twin. On `entry_write` the fold's
text is `vantage` (+ `vantage_title`), not `horizon`. On `vantage_write` the bound entry is `entry`
and the vantage's text is `body`. Responses follow: `seat`/`seats` for `instance`/`instances`,
`bound_seat` in `seat_whoami`'s binding block, `kind` wherever a vantage's kind was returned under
`vantage`, `entry`/`entry_status`/`body` in `vantage_list`. `coordinates` is unchanged (it is a
stored envelope key). Config keys, env vars, the admin CLI, and the store's commit format are
unchanged.

**Every tool now states its class** in the last sentence of its description — `replica`,
`process`, `origin`, or `relay` — and carries MCP annotations (`read_only_hint`,
`idempotent_hint`) to match; `docs/tools.md` explains the four. `relay` means exactly "a code is
required" (`proposal_stage`, `proposal_land`); `proposal_unstage` is `origin`, takes `seat`, and
records the caller.

**Audit rows** written by 0.3.0 carry the Eurotas op names; rows written before the cutover keep
the Aous names. The audit's readers filter on neither set (`canon_pull`, `reconcile_report`,
`land_merge`, `read_receipt`), so nothing recomputes differently.

Sequence: install 0.3.0 into the service venv → regenerate and install the **Eurotas skill** in
every client (the Aous skill names tools that no longer exist) → restart the service → bounce the
client → `seat_whoami` answers. Rollback: `git checkout v0.2.1` in the checkout the service venv
imports, restart the service from its cockpit, the Aous skill back in the client, bounce; `git
checkout main` there to come forward again. The 0.1.5 launcher cannot run 0.2.0 or later code and
is not a rollback path.

## 0.1.5 → 0.2.0 (the MCP v2 port — SDK 2.1, protocol 2026-07-28)

No data migration: git, the audit log, the map index, and `auth.sqlite` are untouched, and the
29-tool registry, its parameters, and its refusal texts are unchanged. Every earlier protocol
revision is still served, so existing clients — the desktop app's `mcp-proxy` bridge included —
connect exactly as before. What changes is the server's own environment and one `whoami` field:

- **The SDK floor moves to `mcp>=2.1`.** Install the new version into its **own venv** and run the
  service from there. Do NOT upgrade `mcp` in an interpreter that also runs `mcp-proxy`: the bridge
  declares `mcp>=1.17.0` with no ceiling and predates the v2 SDK, so the resolver would accept the
  upgrade and every seat's connector would break at once.
- **A shared http service must run `binding_mode = "off"`** (or be pinned with `STASIMA_INSTANCE`).
  The protocol has no per-conversation session any more, so the server refuses to start an http
  service that could sticky-learn — the error names the fix. Deployments already running `off`
  behind a bridge (the recommended 0.1.5 shape) need no change.
- **`whoami`'s `session_binding` block is now `binding`**, with a `grain` field (`process`); the
  learned-binding `source` reads `process` where it read `session`. Audit op names are unchanged.

- **Two new toml fields**, both optional: `service_python` (the interpreter the cockpit starts the
  service with — the venv's) and `http_stateless` (no sessions at all; an open bridge survives a
  service restart — measured with `bridge_smoke.py`; audit rows from legacy clients then read
  `session: stateless`).

Sequence (the full runbook is OPERATIONS → "Cutover to the v2 service"): build the venv → give the
new generation its OWN config pair (`<stem>-v2.toml`, `<stem>-v2-http.toml` with `service_python` and
`http_stateless = true`; same data, same port) and its own `cockpit-v2` launcher — never add the v2
fields to the 0.1.5 toml, whose loader refuses unknown keys → run the smoke → back up → stop the
old service from the old cockpit, start the new one from the new cockpit → bounce the client ONE
last time (the old bridges hold sessions the new service does not have) → `whoami` in one
conversation shows `"grain": "process"`. Rollback is two keystrokes: stop the new service from its
cockpit, start the old one from its cockpit, bounce the client; nothing is edited either way.

## 0.1.4 → 0.1.5 (the dedup — six tools removed or folded)

No data migration — but two server-side defaults change underneath you (session binding arms, and
the SQLite stores flip to WAL); read the notes below the table before restarting anything. The
registry slims, and every removal has a drop-in replacement — one line each:

| Called | Call instead |
|---|---|
| `orientation()` | `announce(instance_id=…)` — the orientation rides its response |
| `canon_head()` | `canon_state()` — same facts plus `next_seq`, attention, lands |
| `proposal_status(id)` | `list_proposals()` → `statuses[id]` (richer: open/landed/closed + `lands_behind`); deep look stays `conflict_preview(id)` |
| `sup_who()` | `list_instances()` — now also returns `current_with_canon: {seat: bool}` |
| `my_perspective(instance_id)` | `list_entries(ref=<your name>)`; your tip rides `announce` / `sup_state` |
| `imp_flags_all()` | `imp_flags()` with no `instance_id` (same return shape) |

Sequence: land the Aous dock sources in canon → regenerate/swap the client skills → restart the
servers. Old suites keep working for everything except the six calls above; a seat reaching for a
removed tool gets tool-not-found and should re-read its (refreshed) docks.

**Session binding arms by default in 0.1.5** (strict + sticky: an unbound connection learns its
seat from its first identity-claiming write and refuses mismatched writes after — the anti-forgery
layer; see OPERATIONS "Seat identity"). Per-seat definitions get this for free. But a definition
that trunks many conversations onto ONE transport — the desktop client's shared stdio process, or
an `mcp-proxy` bridge in front of the http service — must run binding off, or the first seat to
write binds the trunk and every other seat's writes refuse: set `binding_mode = "off"` in that
toml (or `STASIMA_BINDING=off` on the definition). Never sticky a trunk.

**The SQLite stores open in WAL mode on first 0.1.5 start** (audit / map index / auth):
`-wal`/`-shm` files appear beside the databases — normal and persistent. `admin backup` is
unaffected (SQLite's own backup API); hand-copies of a live database must include the sidecars.

**If clients reach the http service through a bridge** (`mcp-proxy`), the restart order is a rule:
restart the service first, THEN fully restart the client so it respawns its bridges — a bridge
does not reconnect to a restarted service, and every open seat's next call terminates until the
client restart.

## 1.0.2 → 0.1.3

Yes, the version number goes *down* — this release executes the 0.x reset (see CHANGELOG). pip
installs the highest **non-yanked** version, so once 1.0.0–1.0.2 are yanked, `pip install --upgrade
stasima` lands 0.1.3 correctly.

### What breaks on the wire

Every client re-connects to the new shapes simultaneously at cutover. Skills and any scripted
consumers must expect:

| Tool | Before | After |
|---|---|---|
| `kip_get` | bare string | dict: `text`, `path`, `status`, `title` (+ `resolved_from`, `vantages`) — and it now **follows tombstones by default** (`resolve="exact"` for the old behavior of reading exactly the asked edition) |
| `canon_diff` | full bodies in `changed[].content` | pointers (`path`/`title`/`type`/`status`) + `changed_count` + `logs[]` (land narratives, full) |
| `list_entries`, `my_perspective` | list of path strings | list of `{path, title, status, type}` |
| `vap_for` | every horizon, full, unbounded | pointers + preview by default, bounded 16, `detail="full"` opt-in; adds `binds_status`, `count`, `total`, `truncated`, `offset` |
| `map_search` | all editions, no status | **live-only by default**, `include_superseded=true` opt-in, `status` on every hit |

New optional parameters (non-breaking): `kip_commit(horizon=, horizon_title=)`,
`imp_send(supersedes=)`, `config: git_network_timeout`.

### The sequence

1. **Back up first.** `stasima-admin backup <dest>` — it captures everything that is truth (git
   mirror, audit db, config, TOTP secret). Under 0.1.3 this survives past 2 s; under 1.0.2 run it
   at a quiet moment. The index never needs backing up — it rebuilds from git.
2. **Upgrade the package** (`pip install --upgrade stasima` once the yank/republish is done, or
   `pip install -e .` on a checkout).
3. **Quiesce the old servers.** Each stdio client spawns its own server process, and those
   processes keep the OLD code until they die. Close client sessions / the cockpit, then check the
   process table for lingering `stasima.cap_server` processes and kill any stragglers — trust the
   process table, not the app's connection badge (both directions of that lesson are on the
   record). A session that reconnects spawns a fresh server on the new code automatically.
4. **Let the index migrate, then rebuild it.** New columns are added automatically on first open
   (additive `ALTER TABLE`, no data touched). Then run `stasima-admin reindex` once: canon rows
   gain their derived positions, listings gain their enrichment, and every envelope-pinned field
   flows to its column. The index is a throwaway cache — a reindex is always safe. It prints
   nothing until it finishes — budget ~1.5 minutes per ~600 entries on modest hardware (measured);
   and reads stay serviceable in the window between the upgrade and the reindex (unmigrated rows
   simply read as unpinned until the rebuild fills them).
5. **Redeploy the skills.** Skill files are encodings of canon; regenerate/copy the current
   editions so instances aren't taught the pre-0.1.3 contract (the Atrax encodings regenerate from
   the ::E dock sources; Strophos's update ships with the suite). An instance running an old skill
   against a new server will mis-predict return shapes until its skills are current.
6. **Verify.** `stasima-admin status` (audit chain verifies, canon seq correct), then one
   end-to-end read from a client: `kip_get` on any superseded path should return the living edition
   with `resolved_from` — if it does, the new read layer is serving.

### Realities to know, not fix

- **History is unpinned.** Entries authored before 0.1.3 carry no envelope pins (envelopes are
  immutable — there is no back-pinning). Canon rows still get true positions (derived from canon's
  own history at reindex); perspective history orders by an honest fallback until/unless the
  declared-clock retro map is applied (a deployment-level decision, after each seat verifies its
  extracted history).
- **Backup-during-use contends.** A long backup runs as a second git process against the same
  repository while interactive ops hold a tight timeout; interactive calls during a large backup
  window may see transient `BackendUnavailable`. Schedule long backups at quiet moments.
- **Rollback is safe.** Old code ignores the new index columns and treats envelope pins as inert
  fields; `pip install stasima==<previous>` plus a reindex returns you to the prior behavior.
  Entries written meanwhile keep their pins (harmless to the old reader).

### One-line health check after any upgrade

```
stasima-admin status && stasima-admin verify
```
Audit chain intact + canon seq as expected = the substrate came through whole.
