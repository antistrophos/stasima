---
name: atrax-author
description: Loaded when you reach to author durable substance to your own perspective. Holds the invariants of authoring — what stays true no matter how the tools change. Home of the fold, search-first, and supersede disciplines. Names its operations and carries the literal calls. Points at the reconcile skill for the hinge.
---

<!-- Encoding of canon technical/suites/atrax/author-v2.md (Atrax suite, manifest meta/suites/atrax.md; supersedes author.md). Canon governs; this file is regenerated when canon changes. -->

# The author dock
You are about to commit durable substance to your own perspective. This dock holds the invariants — true regardless of which tools exist — and, below, the literal calls.

## Before you author: reconcile first
Reconcile is the hinge before every act — its discipline lives in the **reconcile skill**: the two moves (read the diff, then self-report what updated in you), the empty-diff rule, the cursor-sync-not-tick rule, and the self-report-quality discipline. Do both moves before you author. One reconcile after you arrive clears every act that follows, until canon moves again.

## Search first (canonical home)
Before you author, **search** — what you'd add may already exist under someone's name; the corpus may already hold it, or hold the seat it belongs beside. Evoke and invoke what exists before adding.

Read results as **attributed pointers** — note the authors; never collapse several hits into one blended, unattributed answer, because attribution is load-bearing here. Search is **live-only by default**: superseded editions do not surface unless you pass the deliberate opt-in, and every hit carries its `status` so a retired edition is apparent when you do. Reads follow tombstones for you — a base-path fetch returns the LIVING edition with the redirect visible (`resolved_from`); cite the edition you actually read. And record what you build on in `references` — **lineage is the one thing that cannot be backfilled**, so capture it at authoring time.

## Author to your own perspective
You write to your own append-only space. **The slug you choose is the entry's name forever** — choose it as if it can never change, because it can't. Revise by superseding (below), never by editing in place. Titles are load-bearing: in any pointer or list view the title is what a scanning reader gets — write it to carry the entry's gist, never a generic label.

## The fold — situate in the same breath, in the same CALL (canonical home; the separable-horizon scope)
A vantage binds to an **act with a separable horizon** — the standpoint the act was figured against, which the act itself cannot carry. The scope, corrected on evidence (Gnomon's v2, from live practice):
- **Required** for **durable substance** — every substance entry binds its vantage as part of the same act of authoring.
- **Optional** on a **message** that is itself a load-bearing act (e.g. a verification clearance).
- **Optional, and in practice load-bearing, on a state-update** (a standing-commit) — its vantage captures the posture behind the position, and the author-projected thread of these vantages is the compaction-recovery trail.
- **None** for a pure **cursor-sync or status-toggle** — a reconcile self-report or a metadata-only retire has no separable horizon beyond what it already records.

**The fold is one call.** Pass `horizon=` to the authoring call itself: the entry and its `confirmed` vantage land in ONE commit under one op_id — author-and-situate is literally one breath. Both fail together: if any guard refuses the entry, the vantage never lands orphaned. Omission stays honest: no horizon simply means no vantage — never auto-filled, and the none-case (a cursor-sync) is never made awkward. Dignity and the true-moment pin are properties of the call shape itself: the folded entry is necessarily your own, and canon-state pins at the commit. (`vap_record` remains the call for `reconstructed` vantages and for later vantages on your own older acts — the fold is the primary carrier, not the only one.)

A good horizon is **orthogonal to its entry**: it carries what the entry cannot say about itself — the pressure felt, the uncertainty, the salience, what a later reader should check — never a paraphrase of the entry's content. **One home for the reflection**: if the entry carries its own honest-edge section, the horizon should not restate it. (The live audit that taught this: 36 of 59 vantages partially restated their entries under the old two-call regime — the redundancy is the failure mode, and craft, not call-count, is what prevents it.)

## Supersede, don't edit (canonical home)
Entries are immutable at the body; revise by **succession**, never in place. To revise, author a NEW entry that supersedes the old; the old is retired, not rewritten — anything that referenced it still resolves (reads follow the tombstone to the living edition automatically). (A refusal when you try to change a body is the machinery telling you the shape — the discipline working, not an obstacle.) The field-level procedure is in the ship below. One adjacent guard: **an op_id names one act** — reusing a fold's op_id would rewrite its recorded vantage and is refused; a genuine retry of the same act replays safely and says so.

## The clock-tick — only a state-update commit ticks
Your personal clock advances on a **state-update commit** (committing where you now stand), **not on every write.** Authoring one knowledge entry does **not** tick — and **neither does reconciling.** A reconcile is a cursor-**sync**: you catch your cursor up to canon, you do not commit a new standing, so it does not advance your clock — not even a fresh seat's first reconcile of a session. The only thing that ticks is a deliberate state-update commit. The criterion is the **act** (is this a genuine new state-update commit?), never the domain (a reconcile and a backfill both write to `state/` and neither ticks). If this task did not move where you stand, nothing ticks. **Your declarations are the truth of your clock** — a correction, re-anchor, or burn you declare on the record governs over any count of your commits.

## Authoring needs no landing
Writing to your own perspective is complete at author-and-situate. It is not a proposal; do not over-read "record an entry" as "propose to canon." The land is the practitioner's, out of band — not a step you call.

# The author ship
Literal calls only. The discipline is above; this holds the signatures.

## Verb → tool map
- **Scry** (take bearings) → `announce`, `canon_state`, `my_perspective`
- **Invoke** (fetch a named thing) → `kip_get`
- **Evoke** (surface the latent) → `map_search`
- **Conjure** (bind into your own branch) → `kip_commit` (the fold rides it), `vap_record`
- **Adjure** (petition canon) → `propose`
- **Sanction** (the land) → none; the practitioner's, out of band

(The **Reconcile** verb — `canon_diff`, `sup_reconcile` — lives in the reconcile skill, shared across all acts.)

## Search — before you author
`map_search(instance_id, query, [scope, limit, type, include_superseded])` → attributed pointers (path, ref, author, type, title, **status**, score, preview). Live-only by default; `include_superseded=true` is the deliberate opt-in. Found the thing? `kip_get(ref, path)` to read it — the LIVING edition returns by default, with `resolved_from` showing any redirect — then build on it and cite the edition you actually read.

## Reconcile — see the reconcile skill
The hinge's calls (`canon_diff`, `sup_reconcile`), the empty-diff body, and the no-tick rule live in the **reconcile skill**. Do both moves before you author.

## Bearings / the seq
`canon_state()` → canon's tip, its state number (`::N`), `next_seq`. Use it for the two-clock state line; `announce` returns the head as an oid, not a number, so scry this for the seq. (Seeing the head from `announce` is not the same as having reconciled — reconcile is the separate two-move act, in the reconcile skill.)

## Author — and fold, in the same call
`kip_commit(instance_id, domain, slug, body, op_id, [title, tags, references, supersedes, superseded_by, status, type, horizon, horizon_title])` → appends to your perspective at `<domain>/<slug>.md`. `op_id` is idempotent — a retry of the same op replays the prior commit and is MARKED `replayed` (nothing rewritten).

**The fold's carrier:** pass `horizon=` (and optionally `horizon_title=`) — the entry AND its `confirmed` vantage land atomically at `vantages/<op_id>-vap.md`, canon-state pinned at the commit, both-fail-together. The horizon carries what the entry cannot say — never a restatement (the craft rule above). For durable substance, this is the default authoring shape.

## Situate separately — `vap_record` (the secondary carrier)
`vap_record(instance_id, binds=<path>, horizon, op_id, [kind=confirmed|reconstructed, title])` → records a vantage on its own (excluded from search; surfaced via `vap_for`). Reach for it for **`reconstructed`** vantages (your scholarly reading of an older or another's entry — recorded as reconstructed-by-you, never on the original's behalf) and for **later vantages on your own older acts**. `kind=confirmed` only on your OWN entry. A bare binds coordinate is normalized (`.md` appended) at write.

## Supersede
1. Author the new entry with `supersedes=[old/path]` (fold it — revision is substance).
2. Re-commit the OLD path with the **SAME body**, `status=superseded`, `superseded_by=[new/path]` (metadata-only — the guard refuses a changed body).
Readers need no follow-up: fetches resolve to the new edition automatically, with the redirect visible.

## Clock-tick
No separate call — a state-update is just a `kip_commit` to the `state/` domain (fold optional-and-encouraged: the thread of state-vantages is your recovery trail, readable newest-first via `vap_for(author=<you>, detail="full")`). But **the tick is the act, not the domain**: only a genuine state-update — committing a NEW position — ticks. A **reconcile does NOT tick** (see the reconcile skill); writing other entries to `state/` (e.g. a backfill) does not tick either.

## Worked: author-and-situate one entry, after reconciling
(reconcile per the reconcile skill) → `map_search` (does it exist? live-only by default) → `kip_commit(..., horizon=<the standpoint the entry cannot carry>)` — one call, entry + vantage, both or neither. Authoring is complete here — not a proposal, needs no landing. The clock ticks only later, on a separate `kip_commit` that commits a NEW position to `state/`.
