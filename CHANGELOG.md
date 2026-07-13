# Changelog

All notable changes to the Stasima suite. The suite follows the practice's own discipline: entries
are added, never rewritten — corrections appear as later entries.

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
