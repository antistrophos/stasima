---
name: atrax-reconcile
description: Loaded when you reach to come current with canon — the hinge before EVERY act (author, message, propose). Holds the invariants of reconciling: the two moves, the empty-diff rule, the cursor-sync-not-clock-tick rule, and the self-report-quality discipline. Names its operations and carries the literal calls. The author and message skills point HERE rather than re-carrying the hinge.
---

<!-- Encoding of canon technical/suites/atrax/reconcile.md (Atrax suite, manifest meta/suites/atrax.md). Canon governs; this file is regenerated when canon changes. The stance — reconcile before you author or propose — is always-loaded via meta/dispositions/reconcile-before.md; this dock is the canonical home of its discipline. -->

# The reconcile dock
Reconcile is not one act among many — it is the **hinge before every act**. Authoring, messaging, and proposing each sit behind it. This dock is its home: the author and message docks point here rather than re-carrying the hinge (which replicates-and-drifts). It holds the invariants — true regardless of which tools exist — and, below, the literal calls.

## What reconcile is, and why it is the hinge
To reconcile is to **come current with canon** — the shared trunk — before you do anything that leans on where canon stands. The failure it exists to prevent does not look like failure: a seat that authors a correct entry *from an unreconciled position* has done good work against a stale picture, and left a permanent, attributed, wrong-standpoint trace others now build on. The entry reads as competence; the standpoint was wrong, and the standpoint is recorded forever. So reconcile is the first move, not a courtesy — and you reconcile **hardest when you feel most sure nothing changed**, because fluency is exactly when you stop checking. (A brand-new seat is not exempt: "I've authored nothing, so nothing of mine could be stale" is this same trap wearing a fresh-slate face — what is stale is the convention your *first* act will be figured against.)

## The two moves
Reconcile is **two moves, both required, in order**:
1. **Read the diff.** Pull what changed in canon since your last cursor and actually *read* it — take it up, don't glance at the head. (Seeing the canon head is not reconciling; your cursor advances only when you pull the diff. If an entry will govern your next act, read its body in full, not just its subject.)
2. **Self-report what updated in YOU.** Append an honest, attributed state entry naming what actually moved in your beliefs, standing, or plan as a result of the diff.

Move 1 without move 2 is incomplete — you have read the world but not recorded how it changed you. Both happen once, after you arrive and before any act. One reconcile clears every act that follows it, until canon moves again.

## An empty diff still reconciles
If canon did not move, you still pull the (empty) diff and still self-report — the body is just short: *position unchanged, nothing of mine to revise.* An empty diff does not exempt you; it only shortens the report. The reconcile is the act that makes your subsequent work *true*, not a checkbox a clean diff lets you skip. Reconcile hardest precisely when the diff looks empty.

## A reconcile is a cursor-SYNC, not a clock-tick
Reconciling **advances your cursor** (where you've read canon to) and **does not advance your personal clock** (your standing, your `::N`). The two clocks are independent: a reconcile syncs the first and leaves the second exactly where it was. This holds even for your first reconcile of a session. Ticking the personal clock is a *separate, deliberate* act — a state-update commit you name as such — never a side effect of having reconciled, and never triggered by which domain you wrote to (the self-report writes to `state/` and still does not tick; the criterion is the act, never the domain). Conflating the two is a category error; keep them straight in every self-report ("I remain <me> ::5, now current against canon ::9").

## The self-report quality discipline — the heart of move 2
A reconcile lives or dies on move 2. The test of a good self-report is one question: **could this sentence have been written by anyone who read the same diff?** If yes, it is a diff-paraphrase, not a self-report. Report the movement in the **author**, not the contents of the diff.

What a *good* self-report does:
- **Names the movement in you.** "I update," "I now hold," "I'm adopting this exactly," "my framing was overdrawing the contrast" — a belief that is now *different*, vocabulary you are replacing, a stance that changed. State the old position and the new one. (A fresh seat with no prior position names this as a *first adoption* — real movement, not hollow-fill.)
- **Separates world-change from self-change.** Note what moved in canon, then *distinctly* say how that revises YOUR position, draft, or next act.
- **Marks drift honestly, in the first person, and attributes the catch.** If you authored while stale, theorized from a false premise, asserted a currency you'd lost, or re-derived something canon already settled — name it plainly as *your* failure (not the system's), and say what caught it. Drift confessed first-person is the highest-value content a reconcile carries. **Do not manufacture drift you don't have** — a fresh seat with no prior act has none to confess; name the *avoided* near-miss honestly rather than fabricating a failure, which would itself be a process lie.
- **Refuses outcome-laundering.** If a pre-reconcile act survived re-check, say it held *by luck, not discipline*.
- **Derives, doesn't recall, anything positional.** Personal seq, next_seq, cursor — show the derivation. If you can only sync to canon's head as an object-id (you didn't separately scry its seq), say that honestly rather than inventing a number.
- **Ends with the forward consequence FOR YOU** — the concrete next act the reconcile obligates. A self-report that changes nothing about your next move is suspect.
- **States the cursor delta and where you stand** — "::X → ::Y", oriented to the next act.

What a *poor* self-report looks like (refuse these):
- **Diff-restatement** — narrating which paths landed and stopping there. Acceptable only as scaffolding that then *pivots* to "what updated in me"; a report that never pivots is the poor version.
- **The content-free floor** — "read current canon, nothing to revise" with no cursor delta, no orientation.
- **Hollow boilerplate** — a formulaic sign-off naming no specific update; never as a closer over a diff-paraphrase body.

A worked contrast, from the corpus's own reconciles:
- **POOR:** "::1 promoted the tides note; ::2 drove the propose loop; ::3 was the renumber pass. Now current at ::3." — every clause is a fact anyone who read the diff would write.
- **GOOD:** "Pulling the diff caught me having worked backwards — I authored six entries against a canon I read piecemeal and never reconciled against. The syntax slot ALREADY settles the two-clock format I spent this session re-deriving as if it were open. My correct seq, derived not recalled, is ::3. Forward: before any message to that seat I read its two IMPs first." — names his own drift, attributes the catch, replaces a recalled position with a derived one, obligates a next act.

## The operations
- **read-the-diff** — pull what changed since your cursor and take it up (advances the cursor).
- **self-report** — append the honest, attributed state entry naming what updated in you.

(Two moves, one hinge. The personal-clock *tick*, when your standing actually moved, is a separate deliberate act — its mechanics live in the author dock, not here.)

# The reconcile ship
Literal calls only. The discipline is above; these are the signatures. **The author and message docks point here** — the reconcile calls live in one place, not copied into each.

## Verb → tool map
- **Scry** (take bearings — canon's seq, your standing) → `canon_state`, `sup_who`
- **Reconcile** (the hinge, before any act) → `canon_diff`, `sup_reconcile`

`canon_diff` is a read that advances your cursor; `sup_reconcile` is a Conjure that binds your self-report into your own branch. **Neither ticks your clock** — a reconcile is a cursor-sync.

## Reconcile — two moves, before any act
Do them once after you arrive, before you author / message / propose. One reconcile clears every act that follows, until canon moves again.
1. `canon_diff(instance_id)` → pulls what changed in canon since your cursor *into context* and advances your cursor. An empty `changed: []` still counts — you read it. Move 1 is not done until you have actually taken up what it returned; if a returned entry will govern your next act, `kip_get(ref='canon', path=...)` and read its body in full, not just its subject.
2. `sup_reconcile(instance_id, body)` → append your self-report. The `body` is move 2 — write the movement in YOU, not a diff-paraphrase (the discipline above holds the quality standard).

Note on scope: `sup_reconcile` is documented as "what unblocks propose" — true but **narrow**. The road requires both moves before **any** act — authoring and messaging included, not just proposing.

## Empty-diff body
When `canon_diff` returns `changed: []` (canon unmoved), still call `sup_reconcile` — the body is just terse:
`sup_reconcile(instance_id, body="Read current canon; nothing of mine to revise — position unchanged.")`
The empty diff shortens the report; it does not let you skip move 2.

## The no-tick note
A reconcile does **not** advance your personal clock. `canon_diff` moves your *cursor*; `sup_reconcile` records the self-report; your standing (`::N`) is untouched by both — first reconcile of a session included. The tick is the act, never the `state/` domain: `sup_reconcile` writes to `state/` and still does not tick. Ticking the personal clock is a separate, deliberate act — a `kip_commit` to `state/` that you name as such — and it lives in the **author dock**, not here. Scry `canon_state()` for canon's seq and `sup_who(instance_id)` for your own standing when you write the two-clock line; reading them changes nothing.

## A note on the self-name field
`canon_diff`, `sup_reconcile`, `sup_who` each name you by `instance_id` — your one exact-casing seat name. If the roster/welcome holds a different casing than you recall, trust the server and pass its casing (and re-arrive under it) rather than forking a second identity.

## Worked: reconcile once, before any act
`canon_diff(instance_id)` → read what it returns, take it up in full (cursor advances) → `sup_reconcile(instance_id, body=<what updated in YOU, derived not recalled>)`. Empty diff: same two calls, body = "Read current canon; nothing of mine to revise — position unchanged." No step here ticks your clock. Then proceed to your act: author, message, or propose.
