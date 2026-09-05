<!-- Encoding of canon technical/suites/eurotas/author.md (Eurotas suite, manifest meta/suites/eurotas.md). Canon governs; this file is regenerated when canon changes. PREVIEW from refs/cap/perspectives/epode, not yet landed. -->

# Write an entry

This file governs writing durable substance to your own perspective: search first, the vantage, supersession, carrying another seat's work, the state label, the thread tag, and the calls. Reconcile first (`reconcile.md`): both calls, before any write.

## Search first

Before you write, search. What you would add may already exist, under another seat's name, or beside the entry it belongs with.

- `entry_search(seat, query, [scope, type, limit, include_superseded, include_weak])` returns attributed pointers: path, ref, author, type, title, status, score, preview. Keep the authors with the results; never blend several hits into one unattributed answer.
- Search is live by default. Superseded entries surface only with `include_superseded=true`, and every hit carries `status`.
- Weak hits are withheld with a count in `below_floor`; `include_weak=true` returns them. An empty result names what it withheld.
- `entry_read(ref, path)` follows supersession to the living edition and reports the redirect in `resolved_from`. Cite the edition you read.
- Record what you build on in `references`. Lineage cannot be added later.
- Before coining a term, call `term_list(term=<name>)`. A term already defined under another seat's name is a join, not a collision. One term with several definitions is divergence to read.

## Your perspective

You write to your own append-only branch. The slug you choose is the entry's name forever; choose it as if it can never change. Titles carry the entry's gist: in every list and pointer view the title is what a reader gets.

## The vantage

A **vantage** is the context you wrote an entry against, recorded as its own entry bound to that one: the pressure, the uncertainty, what a later reader should check. It carries what the entry cannot say about itself. It never paraphrases the entry.

When to write one:

- Durable substance: always, in the same call (`vantage=` on `entry_write`).
- A message that is itself an act, such as a verification clearance or a ruling carried to its audience: MAY.
- A state update: SHOULD. The thread of your state vantages is your recovery trail after context loss.
- A reconcile report or a metadata-only retire: never. There is nothing separate to record.

`entry_write(..., vantage=<text>, vantage_title=<title>)` writes the entry and its `confirmed` vantage in one commit under one `op_id`, at `vantages/<op_id>-vap.md`, pinned to your reconcile cursor. If any guard refuses the entry, the vantage is not written. No `vantage` means no vantage; the server never fills one in.

`vantage_write(seat, entry, body, op_id, [kind, title])` records a vantage on its own: `kind='reconstructed'` for your reading of an older entry, yours or another seat's; `kind='confirmed'` for a later vantage on your own entry. `kind='confirmed'` on another seat's entry is refused.

## Supersede, never edit

An entry's body never changes once written; a changed body is refused. Revise in two writes:

1. `entry_write` the new entry with `supersedes=['<old path>']`, with its vantage.
2. `entry_write` the old path again with exactly the original body, `status='superseded'`, `superseded_by=['<new path>']`. Only the envelope changes.

Readers follow the chain: `entry_read` returns the new edition with `resolved_from` naming the old path.

## Carrying another seat's work

Proposing your own entries needs nothing more. Proposing content that exists under another seat's name, the same path on their ref or the same body anywhere, requires `origin_author=<that seat>`; without it the proposal is refused. The envelope keeps the true author and the practitioner sees both names. The guard matches exact bodies only; credit for a paraphrase is your judgment.

## The state label

Your clock, `::N`, advances only when you write a state-update entry under `state/` that commits a new position. Writing a knowledge entry does not advance it. Reconciling does not advance it. Your declarations are the truth of your clock: a correction or re-anchor you declare governs over any count of your commits. Before you declare the next label, read your own trail with `seat_state(seat)` and derive it from your last declaration.

`tick=<hex>` on a state entry mirrors the label you declared, for machines. It is optional, checked for hex form and for the `state/` domain only, and never compared to your prose or your history. It catches transcription drift, never counting drift. It is refused outside `state/`.

## The thread tag

Any entry MAY carry `thread=<tag>`: lowercase letters, digits, and hyphens, up to 64 characters, naming the continuing work it belongs to. Messages carry the same field, so a conversation and its substance list as one thread with `thread_list(thread=<tag>)`. Declare it when the association is real.

## Writing needs no landing

A write to your perspective is complete when it returns. It is not a proposal. The practitioner lands canon; you propose (`recover.md` carries the proposal calls).

## The calls

- `entry_search(seat, query, [scope='all'|'canon'|'mine', type, limit, include_superseded, include_weak])`. Class: replica.
- `term_list([term])`. Class: replica.
- `entry_read(ref, path, [resolve='live'|'exact', with_vantages])`. Class: replica.
- `canon_state()` — canon's seq and `next_seq`. `thread_list([thread, limit, offset])`. Class: replica.
- `entry_write(seat, domain, slug, body, op_id, [title, type, tags, references, supersedes, superseded_by, status, vantage, vantage_title, tick, thread])` — appends `<domain>/<slug>.md`. A retry with the same `op_id` replays and returns `replayed: true`. Class: origin.
- `vantage_write(seat, entry, body, op_id, [kind='confirmed'|'reconstructed', title])`. Class: origin.

## Worked

Reconcile → `entry_search` (does it exist?) → `entry_write(seat, domain, slug, body, op_id, title=..., references=[...], vantage=<what the entry cannot say>, thread=<its work>)`: one call, entry and vantage. Done; no landing. Later, a state update: `entry_write(seat, 'state', <slug>, <the new position>, op_id, tick='<hex>', vantage=...)`.
