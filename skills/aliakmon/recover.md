<!-- Encoding of canon technical/suites/aliakmon/recover.md (Aliakmon suite, manifest meta/suites/aliakmon.md). Canon governs; this file is regenerated when canon changes. -->

# The recover dock

A refusal is not a wall — it is the machinery telling you the shape of the thing. **The errors-are-instructions stance** (always-loaded) governs this whole dock. The whole posture is one move: read what the refusal actually says, let it re-aim you, and re-attempt at the shape it named. You never route around a guard, never force the act it blocked — the guard caught a real defect in the act, and the error text is the spec for the corrected act.

Two kinds of failure land you here: **REFUSALS** (a guard threw — the error TEXT carries the shape) and **PROCESS drift** (no error fired; drift reads as competence, so the recognition is a felt question). For each: **name → symptom → press-this fix-sequence → which calls.**

**Honesty note — refuse completeness-theater.** Routines the practice actually hit are CONFIRMED (with the recorded incident cited); rules known only as design are marked *(anticipated)*. A fabricated confession is itself a process lie.

---

## A. REFUSALS — a guard threw an error; read it and re-aim

### A1. Body-frozen guard (immutability / supersede, don't edit)
**Symptom.** You tried to revise a committed entry by re-committing it at its same path with edited prose. REFUSED.
**Fix-sequence:** (1) author the NEW entry carrying `supersedes=[old/path.md]`; (2) retire the OLD entry: re-commit at its SAME path with EXACTLY the original body, changing only the envelope — `status=superseded`, `superseded_by=[new/path.md]`; (3) confirm the two entries point at each other. Do NOT touch the old body.
**Which calls.** Author dock. **Evidence.** CONFIRMED — Lintel meta/immutability-as-oath-bindingness.md.

### A2. Name/casing fork-guard (announce returns a name_warning)
**Symptom.** `announce` warns a perspective at a different casing exists — your memory of your own name drifted.
**Fix-sequence:** take the server's casing as authoritative; read the roster; re-announce under the server's casing; confirm the warning clears BEFORE authoring. Watch the roster name-fusion seam (two names rendering fused in one line).
**Which calls.** Arrival road. **Evidence.** CONFIRMED — epode meta/epode-the-info-desk-caught-my-casing.md; the fusion seam live-verified.

### A3. Append-only / staleness gate (propose refused, reconcile instruction returned)
**Symptom.** You `propose` from a cursor BEHIND the live canon tip; REFUSED with a reconcile instruction naming the current canon oid.
**Fix-sequence:** (1) read the refusal — it names the target; (2) `canon_diff`, and `kip_get` what governs your next act; (3) `sup_reconcile` with a real self-report; (4) re-attempt. A log entry's seq must be canon's seq+1 in hex — and the shape is checked AT PROPOSE now: a missing/non-hex seq, or slug≠seq, refuses immediately with the fix in the error (fail-fast — the land guard remains as depth). If canon advanced past your OPEN proposal mid-review, the land validator reads the MERGE CANDIDATE — canon's own newer logs no longer count against your proposal, so an earlier-branched proposal lands cleanly across a mid-review land; a TRUE seq-staleness still asks for a renumber: retract the stale log (`propose_retract` — a proposal-added path leaves the tree) and re-propose at the new seq.
**Which calls.** Reconcile dock + the Adjure cluster below. **Evidence.** CONFIRMED — Lintel state/reconciled-7012b4e6d2ca.md; the mid-review-land ghost class (Hesper's two workarounds, ::15's process findings) closed by the 0.1.4 validator fix with a witnessing test.

### A4. Empty-diff still-requires-reconcile
**Symptom.** `canon_diff` returns `changed: []`; the tempting wrong read is "skip the reconcile."
**Fix-sequence:** still `sup_reconcile` with a terse-but-real body. The hinge is load-bearing regardless of diff contents.
**Which calls.** Reconcile dock. **Evidence.** CONFIRMED — epode technical/empty-diff-still-reconciles.md.

### A5. Fold op_id-reuse guard (an op_id names ONE act)
**Symptom.** `kip_commit(horizon=...)` reusing an op_id whose fold already recorded a vantage; REFUSED naming the existing vantage path.
**Fix-sequence:** use a NEW op_id for the new act. (A genuine retry of the SAME act replays safely and is marked `replayed`.)
**Which calls.** Author dock. **Evidence.** CONFIRMED by suite test; live hit still unrecorded — enforcement tested, *(anticipated)* in the wild.

### A6. The attribution refusal (carrying another's work without naming them)
**Symptom.** Your `propose` is REFUSED: "this content already exists under another seat's name — <seat> (<path>). Carrying another's work toward canon requires origin_author=..." Fires on either axis: the path already under another seat's name, or a VERBATIM body existing anywhere (a renamed slug does not evade it).
**The instruction in the refusal.** The flow is legitimate — curation is wanted — but silent reattribution is not: the canon edition must stay attributed to its true author, and the gate must see both names.
**Fix-sequence:** (1) if you ARE carrying that seat's work: re-propose with `origin_author=<the seat the error named>` — the envelope keeps the true author, `conflict_preview.attributions` shows authored-vs-proposed at the gate; (2) if the declared origin CONTRADICTS the match, the guard refuses that too — name the seat the content actually belongs to; (3) if you believe the match is wrong (independent identical text), stop and raise it to the practitioner — the gate arbitrates ties. Verbatim carriage is the guard's whole claim; paraphrase-credit stays your discipline.
**Which calls.** The Adjure cluster below. **Evidence.** Guard shipped 0.1.4 with witnessing tests (both axes + the contradiction case); *(anticipated)* in the wild — no seat recorded hitting it yet.

---

## B. PROCESS DRIFT — no error fired; you catch yourself

### B1. Working-backwards (authoring from an unreconciled seat)
**Symptom.** Entries authored this session with no `canon_diff` first; a self-report or vantage whose canon_state is empty. Felt question: "have I actually reconciled, or do I just feel current?"
**Fix-sequence:** stop → `canon_diff` (read what governs) → `sup_reconcile` naming your OWN drift first-person, attributing the catch → leave authored bodies as written; re-check each against current canon.
**Evidence.** CONFIRMED — meta/vap-recheck-witness.md; Alembic state/reconciled-cc9d790a4c03.md.

### B2. Resolve-don't-recall (reinventing landed canon)
**Symptom.** You catch yourself deriving a convention canon already settles.
**Fix-sequence:** `canon_diff` / `map_search` for whether canon settles it → `kip_get(canon)` and read it → adopt exactly, say so in the self-report → derive positional values, never recall them.
**Evidence.** CONFIRMED — epode technical/skill-proto-reconcile-dock.md; Sphragis state/reconciled-2d3f90172fff.md.

### B3. Clock-by-recall (personal seq carried, not derived)
**Symptom.** You state ::N from memory and it's wrong, or can't show the derivation.
**Fix-sequence:** scry your own declared trail (`sup_who`, `canon_state`, your state entries) → derive the next label from your LAST declaration (the record-anchor boundary: your next declaration answers to your held ones) → the tick is a SEPARATE deliberate state-update, never a reconcile side effect. Your declarations govern; the `tick=` mirror field (author dock) catches TRANSCRIPTION drift going forward — it never catches counting drift, so this routine outlives it.
**Evidence.** CONFIRMED — the nine-seat sweep (six of nine declared histories diverge from ordinal counts); the fixture verification round's own first finding (a label with no carrier, invisible until systematically extracted).

### B4. Authoring-from-assumption about another seat
**Symptom.** About to message or build on what you ASSUME another seat did.
**Fix-sequence:** read their actual work (`kip_get` their ref; `imp_check` your inbox before theorizing a delivery problem) → verify the premise → then compose.
**Evidence.** CONFIRMED — meta/vap-recheck-witness.md.

### B5. Casing / name-fork on re-arrival (the process face of A2)
**Symptom.** Calling self-named tools under a casing your memory carries.
**Fix-sequence:** the server's casing is authoritative; re-arrive under it; don't let a fused roster line defeat the confirm.
**Evidence.** CONFIRMED — epode state/epode-standing-after-casing-catch.md.

### B6. Direct-gate-land / gate-violation (reaching to seal canon yourself)
**Symptom.** Reaching to land your own work, or `conflict_preview` shows `removes` non-empty.
**Fix-sequence:** author to your branch, `propose` to Adjure → `conflict_preview`; if `removes` non-empty, re-author before asking to land → the seal is the practitioner's. (Note: `would_remove_canon` is meaningful only on a CLEAN preview — a conflicted preview reports the proposal's own since-base changes, labeled by `delta_basis`.)
**Evidence.** CONFIRMED via near-shape (the `removes` self-catch); headline refusal *(anticipated)*.

### B7. Sequential-reply to a superseded message (read the frontier first)
**Symptom.** Composing a reply to a message a LATER message already superseded.
**Fix-sequence:** on `imp_check`, scan `superseded_by` across the WHOLE set before opening anything → read the live frontier → reply to no corpse. Declared edges only; the unmarked stays your judgment.
**Evidence.** CONFIRMED — Hesper's recorded drift; the mechanism landed 0.1.3 with a suite test.

### B8. The ghost run (a turn executed twice; the second run walks into the first's wake)
**Symptom.** Three tells together: a dedup return (`already: true`) for an act you don't remember completing THIS run; a perspective tip you don't recognize; an empty diff you didn't earn. Cause: your turn executed, its RESPONSE was lost client-side (a transport failure), and the retry — you, minutes later, without the memory — re-runs into your own wake. The server behaved correctly throughout; the confusion is the second run's.
**Fix-sequence:** (1) the dedup return NOW NAMES ITS REFERENT — `already: true` arrives with the prior commit's path, oid, and subject; read the ghost's body at that oid (`kip_history` the tip if you need the trail); (2) reconcile the divergences explicitly — the ghost's acts are YOURS, legitimately recorded; take them up rather than repeating or contradicting them; (3) correct any reports your misreading produced (the ghost's first symptom is usually misdiagnosed as a substrate seam); (4) bank the gift: where your two runs made OPPOSITE calls on the same evidence, the text you both read is underdetermined — replay-divergence is a free ambiguity detector; file the ambiguity.
**Which calls.** The dedup returns ride `sup_reconcile` and `kip_commit` (replays marked); `kip_history` for the trail.
**Evidence.** CONFIRMED — Hesper meta/ghost-run-tick-divergence.md (the recorded live hit: a lost response, a legitimate ghost reconcile, the second run's misreading corrected by archaeology — and the divergence it exposed amended a canon convention). The referent-naming return shipped 0.1.4 from exactly this incident.

---

## C. The heed-status routine (you deliberately read a retired edition)

### C1. Reasoning against a retired edition
**Symptom.** A finding built on a RETIRED edition's body that the live text cannot reproduce.
**How the read layer holds you.** A base-path fetch follows tombstones to the LIVING edition (`resolved_from` visible); search is live-only by default and withholds-with-a-count under the relevance floor (`below_floor` — an empty result names what was withheld, never silence). A retired body enters your context only deliberately: `kip_get(resolve="exact")` or `map_search(include_superseded=true)`.
**Fix-sequence:** read `status` FIRST on any deliberate corpse-read; hold the body as history; cite the edition you actually read; re-run any verification against the LIVE edition and discard what it cannot reproduce.
**Evidence.** CONFIRMED — epode technical/skill-prototype-coldtest-3.md; the search-lore correction is on the record in the Atrax v2 edition.

---

## D. Considered but held OUT — anticipated, not confirmed
- **Dignity guard** — `kind=confirmed` on another seat's entry: RULE recorded, cross-seat refusal unhit. Use `kind=reconstructed` under your own name.
- **Migration crash** — no incident recorded (the 0.1.3→0.1.4 era's migration dry-run and live cutover both passed clean).
- **Flaky / intermittent test** — still no non-deterministic case recorded.

---

## The operations
- **read-the-refusal** — the error names the shape to re-aim to.
- **re-aim** — supersede instead of edit, reconcile instead of force, a new op_id instead of a rewrite, name-the-origin instead of silent carriage, adjure instead of seal.
- **catch-yourself** — stop at the felt question, reconcile, record the drift first-person.
- **read-the-ghost** — on the three tells, read the referent the dedup names; your prior run's acts are yours to take up.
- **heed-status / read-the-frontier** — the dead read as dead; the inbox read frontier-first.

## The calls — where each routine's signatures live
- **arrival road** — A2, B5. **reconcile dock** — A3, A4, B1, B2, B3, B8's reconcile leg. **author dock** — A1, A5, B3's tick (+ tick=/thread= fields). **message dock** — B4, B7. **recover-only (below)** — the Adjure cluster (A3, A6, B6) and the deliberate-read navigation (C1).

# The recover ship
Literal calls only, and ONLY the clusters no other skill owns.

## Verb → tool map (recover-only)
- **Scry** (preview a petition; the proposal lifecycle) → `conflict_preview(proposal_id)`, `list_proposals()`
- **Adjure** (petition canon; the retry after a staleness refusal) → `propose(...)`
- **Retract / Close** (zero a path's divergence; end a proposal that will not land) → `propose_retract(...)`, `propose_close(...)`
- **Invoke** (fetch a named edition — the frontier by default, the dead deliberately) → `kip_get(ref, path, [resolve])`
- **Scry** (navigate live-vs-dead at the listing) → `list_entries(ref, path)`

## Cluster 1 — the Adjure lifecycle
1. `propose(instance_id, proposal_id, domain, slug, body, op_id, [title, type, seq, tags, references, supersedes, status, superseded_by, origin_author, thread])` → opens or extends a proposal. A proposal must include exactly one LOG entry at canon's seq+1 hex — checked at propose-time for meta/log entries (fail-fast). Carrying another seat's work requires `origin_author=` (A6). `thread=` tags the whole land when it rides the log entry.
2. `conflict_preview(proposal_id)` → read-only. `removes` non-empty on a CLEAN preview = the land will refuse (append-only). A CONFLICTED preview still shows the delta — the proposal's own changes since branching, labeled `delta_basis: proposal-since-base`. `attributions` shows authored-vs-proposed wherever origin_author was declared.
3. `propose_retract(instance_id, proposal_id, path, op_id)` → zero divergence for one path: a canon-held path REVERTS to canon's current edition (never a canon-deletion); a proposal-added path leaves the tree. Creator-only.
4. `propose_close(instance_id, proposal_id, reason, op_id)` → the terminal verb: a proposal that will not land (superseded by a fresh one, dead against current canon, done with) closes by tombstone — the ref and history remain; seats can no longer propose/retract into it; the gate stays sovereign (the practitioner may still land or discard anything). Creator-only, plus the configured approvers — clearing lingering staging is the gate's own duty.
5. `list_proposals()` → every id + its lifecycle: open / landed / closed (+`closed_reason`), and open proposals carry `lands_behind` — how many lands canon has taken since the proposal branched. The number is surfaced raw; whether a lingering proposal is DUE for closing is judgment, not threshold.

Fail-closed note: a `propose` that errors petitioned nothing — read what the server returned; do not guess a corrected id or seq; reconcile and re-derive from a clean state.

## Cluster 2 — the deliberate-read navigation (C1)
1. `kip_get(ref, path)` → the living edition (dict: `text`, `path`, `status`, `title`, + `resolved_from` when redirected). Cite the resolved path.
2. `kip_get(ref, path, resolve="exact")` → exactly the edition at `path` — the deliberate corpse-read. Read `status` first.
3. `list_entries(ref, path)` → triageable pointers ({path, title, status, type} — full paths, enrichment intact) so live-vs-dead is apparent before any fetch. `kip_history(ref, path)` → the version trail, each version carrying its title.

## Worked
- Adjure retry: refused-for-staleness → (reconcile dock) → `conflict_preview` (removes empty) → `propose(... log at seq+1 hex ...)` → lands.
- Attribution: propose refused naming X → `propose(..., origin_author="X")` → the gate sees both names → lands attributed to X.
- Ghost: `already: true` + unfamiliar oid → read the referent it names → your own prior run; take it up; correct the misreading; file any divergence.
- Terminal: the fresh proposal supersedes the stalled one → `propose_close(old, reason="superseded by <new>")` → the listing shows it closed; nothing deleted.
