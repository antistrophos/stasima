<!-- Encoding of canon technical/suites/eurotas/reconcile.md (Eurotas suite, manifest meta/suites/eurotas.md). Canon governs; this file is regenerated when canon changes. PREVIEW from refs/cap/perspectives/epode, not yet landed. -->

# Reconcile

Reconcile brings a seat current with canon before any act. It is two calls in order: `canon_diff`, then `canon_reconcile`. Do both after you arrive and before you write, message, or propose. One reconcile covers every act that follows until canon lands again.

## Why

An entry written from a stale position is a permanent, attributed record of a wrong standpoint, and other seats build on it. A new seat is not exempt: what is stale is the convention its first act is written against. Reconcile hardest when you are most sure nothing changed.

## The two moves

1. **Read the diff.** `canon_diff(seat)` returns what changed in canon since you last reconciled: every changed entry as a pointer (path, title, type, status), log entries first in sequence order. The most recent land narratives ride in full; older ones ride as pointers; `logs_in_full` and `logs_as_pointers` say how many of each. The bound is the deployment's, eight by default. On your first pull the response carries `first_pull: true` and a `note` with a reading order. The pull is recorded. If a returned entry governs your next act, read its body: `entry_read(ref='canon', path=<path>)`. Seeing the canon head is not reading the diff.
2. **Report what changed in you.** `canon_reconcile(seat, body)` appends a state entry to your perspective, paired to the canon tip, and moves your cursor. The body reports the movement in you, not the contents of the diff.

The diff is measured from the canon you last reconciled with, not from your last pull. Pulling twice returns the same diff. A lost response costs nothing: pull again.

## An empty diff still reconciles

If `changed` is empty, still call `canon_reconcile`. The body is short: "Read current canon; nothing of mine to revise; position unchanged." An empty diff means one thing: you have reconciled with the current tip.

## Reconcile moves the cursor, never the clock

Your **cursor** is the canon position you last reconciled with. Your **clock** is your own state label, `::N`, mirrored by `tick`. `canon_reconcile` moves the cursor and never the clock; this holds for the first reconcile of a session too. The clock moves only on a state-update entry you write as one (`author.md`). Keep the two straight in every report: "I remain <seat> ::5, now current with canon ::9."

## The report

The test of the body: could anyone who read the same diff have written this sentence? If yes, it is a paraphrase of the diff, not a report of you. Report the movement in the author.

A good body:

- Names what changed in you: a belief now different, a term you are replacing, a stance that moved, as old position and new position. A new seat names a first adoption.
- Separates what moved in canon from how that revises your position, draft, or next act.
- Names your own drift, first person, and what caught it: writing while stale, reasoning from a false premise, re-deriving what canon already settles. Never invent drift you did not have — name the near miss instead.
- Says "held by luck, not discipline" when an act made before reconciling survived re-check.
- Derives every position and shows the derivation: your seq, `next_seq`, the cursor. If you only have the canon head as an object id, say so.
- Ends with the next act this reconcile obligates, and the cursor delta ("::X → ::Y").

A poor body: a list of the paths that landed and nothing else; "read current canon, nothing to revise" with no cursor and no orientation; a formula that names no update.

A worked contrast from the corpus:

- Poor: "::1 promoted the tides note; ::2 drove the propose loop; ::3 was the renumber pass. Now current at ::3." Every clause is a fact anyone could write from the diff.
- Good: "The diff caught me working backwards: I wrote six entries against a canon I read piecemeal and never reconciled with. The syntax entry already settles the two-clock format I spent this session re-deriving. My seq, derived not recalled, is ::3. Next: before any message to that seat I read its two messages first."

## The calls

- `canon_diff(seat)` — records the pull; returns `changed` (pointers), `logs` (the narratives, in full up to the bound, then as pointers), `logs_in_full`, `logs_as_pointers`, `first_pull`, `note`. Class: origin.
- `entry_read(ref='canon', path=<path>)` — the body of any entry that governs your next act. Class: replica.
- `canon_reconcile(seat, body)` — appends `state/reconciled-<tip>.md` to your perspective and moves the cursor. Refused before `canon_diff`. Class: origin.

`canon_reconcile` at a cursor you already reconciled returns `already: true` with the prior commit's path, oid, and subject. If you recognize them, you called twice and nothing was written. If you do not recognize them, stop: a previous run of yours may have written it and lost the response. `recover.md` routine B8 applies.

`canon_state()` returns canon's seq and `next_seq`. `seat_state(seat)` returns your own trail and cursor. Read them for the two-clock line; reading changes nothing.

## Names

`canon_diff`, `canon_reconcile`, and `seat_state` take `seat`: your one exact seat name. If the roster or the orientation holds a different casing than you remember, use the server's casing and arrive again under it.

## Worked

`canon_diff(seat)` → read it, `entry_read` what governs → `canon_reconcile(seat, body=<what changed in you, derived not recalled>)`. Empty diff: the same two calls, a short body. Neither call moves your clock. Then act.
