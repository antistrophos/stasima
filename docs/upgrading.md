# Upgrading

The cutover checklist for a **live deployment** moving between suite versions. Written for the
practitioner running the upgrade; the suite's own discipline applies — trust the process table over
status badges, back up before you touch anything, and prefer boring sequences to clever ones.

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
