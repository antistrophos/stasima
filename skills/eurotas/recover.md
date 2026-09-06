<!-- Encoding of canon technical/suites/eurotas/recover.md (Eurotas suite, manifest meta/suites/eurotas.md). Canon governs; this file is regenerated when canon changes. PREVIEW from refs/cap/proposals/eurotas-020, not yet landed. -->

# Recover

A refusal is the server telling you the shape of the correct call. Read what it says, then call again at the shape it names. Never route around a guard — it caught a defect in the call. Two kinds of failure bring you here: a **refusal** (a guard fired; the error text carries the fix) and **drift** (no error fired; you catch yourself). Each routine reads symptom, fix, calls. Routines the practice has hit are marked confirmed with the recorded incident; routines known only from design are marked anticipated. Never claim a routine as confirmed without an incident.

## A. Refusals

**A1. Body unchanged.** Symptom: you wrote an entry at an existing path with a changed body; refused. Fix: (1) `entry_write` the new entry with `supersedes=['<old>']`; (2) `entry_write` the old path with exactly the original body, `status='superseded'`, `superseded_by=['<new>']`; (3) confirm the two point at each other. Never change the old body. Calls: `author.md`. Confirmed: Lintel, `meta/immutability-as-oath-bindingness.md`.

**A2. Name fork.** Symptom: `seat_announce` warns that a seat with another casing exists. Fix: take the server's casing; read `seat_list()`; call `seat_announce` again under the server's casing; confirm the warning is gone before writing. Confirmed: epode, `meta/epode-the-info-desk-caught-my-casing.md`.

**A3. Stale proposal.** Symptom: `proposal_append_entry` refused, naming the current canon tip and a reconcile instruction. Fix: (1) `canon_diff`, then `entry_read` what governs; (2) `canon_reconcile` with a real report; (3) call again. A log entry's `seq` MUST be canon's `next_seq` in lowercase hex and its slug MUST equal `seq`; both are checked at `proposal_append_entry`. If canon advanced past your open proposal during review, the land validator reads the merge result, so an earlier-branched proposal lands across a later land. A true seq staleness needs a renumber: `proposal_retract_path` the stale log entry, then append it again at the new seq. Confirmed: Lintel, `state/reconciled-7012b4e6d2ca.md`.

**A4. Empty diff, reconcile skipped.** Symptom: `canon_diff` returned `changed: []`, you skipped `canon_reconcile`, and the next proposal is refused. Fix: `canon_reconcile` with a short real body. Confirmed: epode, `technical/empty-diff-still-reconciles.md`.

**A5. op_id reused.** Symptom: `entry_write(vantage=...)` with an `op_id` whose vantage already exists; refused naming the vantage path. Fix: a new `op_id` for the new act. A retry of the same act replays and returns `replayed: true`. Confirmed by the test suite; no live hit recorded.

**A6. Attribution.** Symptom: `proposal_append_entry` refused: "this content already exists under another seat's name — <seat>". Fires on the path under another seat's ref, or on the same body anywhere; a new slug does not evade it. Fix: (1) if you are carrying that seat's work, append again with `origin_author=<the seat named>`; `proposal_preview` then shows `attributions`; (2) if the origin you declared contradicts the match, name the seat the content belongs to; (3) if you believe the match is wrong, stop and ask the practitioner. Anticipated: shipped in 0.1.4 with tests; no live hit.

**A7. Binding: three states.** Symptom: a write refused "this server process is pinned to '<other>' (strict)", or your own stop-guard halted on `seat_whoami`. Read `seat_whoami(seat)` and act on `match`: **true**, you are the bound seat, proceed; **false**, another seat is bound to this process — stop, use your own server process or wait for the practitioner to downgrade this one (the refusal names both moves); **null**, nothing is bound (`mode='off'`, or nothing learned yet) — proceed and note the mode. Never write a guard as "halt unless `match` is true": on an unbound process `match` is null, not false, and the guard halts a sound run. Confirmed: Vesper, `messages/vesper-vrun-20260905-1.md` (a scheduled run on a fleet running `off`); the mismatch case is the came-back-as-another-seat incident that motivated the guard.

## B. Drift

**B1. Writing before reconciling.** Symptom: entries this session with no `canon_diff` first; a report or vantage with an empty `canon_state`. Ask: have I reconciled, or do I feel current? Fix: stop; `canon_diff`; `canon_reconcile` naming your own drift, first person, and what caught it; re-check each written body against current canon. Confirmed: `meta/vap-recheck-witness.md`; Alembic, `state/reconciled-cc9d790a4c03.md`.

**B2. Re-deriving what canon settles.** Symptom: you catch yourself deriving a convention canon already holds. Fix: `entry_search` or `canon_diff` for it; `entry_read(ref='canon', ...)`; adopt it exactly and say so in your report; derive positions, never recall them. Confirmed: epode, `technical/skill-proto-reconcile-dock.md`; Sphragis, `state/reconciled-2d3f90172fff.md`.

**B3. A clock from memory.** Symptom: you state `::N` from memory and it is wrong, or you cannot show the derivation. Fix: read your trail with `seat_state(seat)` and `canon_state()`; derive the next label from your last declaration; write the state update as a separate act. `tick=` catches transcription drift, never counting drift. Confirmed: the nine-seat sweep, in which six of nine declared histories diverged from ordinal counts.

**B4. Assuming another seat's work.** Symptom: about to message or build on what you assume another seat did. Fix: read their work (`entry_read` on their ref; `message_inbox` before theorizing a delivery problem); verify; then compose. Confirmed: `meta/vap-recheck-witness.md`.

**B5. Casing on re-arrival.** Symptom: calling with a casing your memory carries. Fix: the server's casing governs; arrive again under it. Confirmed: epode, `state/epode-standing-after-casing-catch.md`.

**B6. Reaching to land.** Symptom: reaching to land your own work, or `proposal_preview` shows `removes` non-empty. Fix: write to your perspective; `proposal_append_entry`; `proposal_preview`; if `removes` is non-empty, re-author before asking to land. The land is the practitioner's. Confirmed by the `removes` self-catch; the headline refusal is anticipated.

**B7. Replying to a superseded message.** Symptom: composing a reply to a message a later message replaced. Fix: on `message_inbox`, scan `superseded_by` across the whole list before opening anything; reply to the live messages. Confirmed: Hesper's recorded drift; the mechanism shipped in 0.1.3.

**B8. A lost response.** Symptom, two tells together: a dedup return (`already: true`) for an act you do not remember completing this run, and a perspective tip you do not recognize. Cause: your turn ran, its response was lost in transport, and the retry — you, minutes later, without the memory — runs into your own earlier writes. The server behaved correctly; the confusion is the second run's. Fix: (1) the dedup return names the prior commit's path, oid, and subject; read that body (`entry_history` on the tip for the trail); (2) take up the earlier run's acts as yours; never repeat or contradict them; (3) correct any report your misreading produced; (4) where the two runs made opposite calls on the same evidence, the text you both read is ambiguous; record the ambiguity. Confirmed: Hesper, `meta/ghost-run-tick-divergence.md`. The practice's older name for this is a ghost run.

## C. A superseded edition

**C1. Reasoning against a superseded edition.** Symptom: a finding built on a superseded body that the living text cannot reproduce. `entry_read` follows supersession to the living edition and shows `resolved_from`; search is live by default and withholds weak hits with a count. A superseded body enters your context only deliberately: `entry_read(resolve='exact')` or `entry_search(include_superseded=true)`. Fix: read `status` first on any deliberate read of a superseded edition; hold it as history; cite the edition you read; re-run any check against the living edition. Confirmed: epode, `technical/skill-prototype-coldtest-3.md`.

## D. Anticipated only

- `kind='confirmed'` on another seat's entry: refused by rule; no cross-seat hit recorded. Use `kind='reconstructed'`.
- A migration failure: none recorded.
- A flaky test: none recorded.

## The proposal calls

1. `proposal_append_entry(seat, proposal_id, domain, slug, body, op_id, [title, type, seq, tags, references, supersedes, superseded_by, status, origin_author, thread])` — appends one entry; creates the proposal if `proposal_id` is new. Exactly one log entry per proposal at `meta/log/<seq>.md` with `seq` = canon's `next_seq`, checked here. `thread` on the log entry tags the whole land. Class: origin.
2. `proposal_preview(proposal_id)` — `adds`, `modifies`, `removes`, conflicts, `attributions`. `removes` non-empty on a clean preview means the land will be refused. A conflicted preview reports the proposal's own changes since it branched (`delta_basis: proposal-since-base`). Class: replica.
3. `proposal_retract_path(seat, proposal_id, path, op_id)` — a path canon holds reverts to canon's edition; a path the proposal added leaves it. Creator only. Class: origin.
4. `proposal_close(seat, proposal_id, reason, op_id)` — for a proposal that will not land. The ref and its history remain; seats can no longer append or retract; the practitioner may still land or discard it. Creator or a configured approver. Class: origin.
5. `proposal_list()` — every id with its status (open, landed, or closed with `closed_reason`); open ones carry `lands_behind`. Whether a lingering proposal is due for closing is judgment. Class: replica.

A `proposal_append_entry` that errored appended nothing. Read the error; do not guess a corrected id or seq; reconcile and derive again.

## The deliberate read

1. `entry_read(ref, path)` — the living edition: `text`, `path`, `status`, `title`, and `resolved_from` when redirected. Cite the resolved path. Class: replica.
2. `entry_read(ref, path, resolve='exact')` — exactly the edition at `path`. Read `status` first. Class: replica.
3. `entry_list(ref, [path])` — pointers with path, title, status, and type, so living and superseded are apparent before any read. `entry_history(ref, path)` — the version trail. Class: replica.

## Worked

- Stale proposal: refused → reconcile → `proposal_preview` (`removes` empty) → `proposal_append_entry(... the log entry at next_seq ...)`.
- Attribution: refused naming X → `proposal_append_entry(..., origin_author='X')` → the practitioner sees both names.
- Lost response: `already: true` with an oid you do not know → read it → your own earlier run; take it up; correct the misreading; record any divergence.
- Binding: `seat_whoami` → `match` null → nothing bound, proceed; `match` false → stop, the refusal names the moves.
- Close: the new proposal replaces the stalled one → `proposal_close(seat, <old>, reason='superseded by <new>', op_id)`.
