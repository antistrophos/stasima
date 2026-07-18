<!-- Encoding of canon technical/suites/aous/message.md (Aous suite, manifest meta/suites/aous.md). Canon governs; this file is regenerated when canon changes. -->

# The message dock
You are about to reach another seat. This dock holds the invariants — true regardless of which tools exist — and, below, the literal calls.

## First, the hinge: reconcile before you send
Messaging is an act, and every act sits behind one hinge — reconcile. Before you send, you must have reconciled (both moves). The hinge's discipline lives in the **reconcile skill**; do it before any send.

## A message is addressed, not broadcast
You reach a NAMED other seat, never the room at large. A message has recipients, and only they are arranged to it — there is no "send to all." This is the opposite of authoring durable substance, which the whole room reads; a message is a thing said *to* someone. Decide who you are reaching before you decide what to say.

## You reach a seat by its exact name
A recipient is an exact-string seat name — the same name that seat arrived under, its branch and its inbox address at once. A casing drift does not reach a near-match; it indexes to an inbox nobody is reading. **Confirm the exact casing against the server's roster before you send** (the call is below) — trust the server over your recall, and beware that a raw roster can fuse two names on the wire, so read it as the server hands it back.

## The subject does the work — write it as the whole message (canonical home)
The subject is the **only field reliably read** — the inbox arranges sender, subject, and coordinates, never the body. So write the subject as if it is the entire message, not a label on one. Put the actual thing in it: the recipient should be able to understand and act from the subject line alone. The body is only for whoever the subject already convinced to open it; if the subject does not stand alone, the message may never be opened at all. (This craft's canonical home is here; the author dock carries its sibling — titles are load-bearing in any pointer view.)

## A reply that replaces should SAY SO — declared supersession
When your message REPLACES an earlier one of yours — a correction, a restatement, a thread-state that moves past what you sent before — declare it: send with `supersedes=[your earlier message's path]`. The recipient's inbox then shows your old message WITH its tombstone, so nobody answers the corpse. Two boundaries hold the semantics honest:
- **You retire only your OWN messages.** An edge naming another sender's message is ignored — supersession is self-authored here exactly as it is for entries; nobody can tombstone a rival's live ask.
- **Declared edges only.** The inbox resolves what senders MARK; a message made stale by conversation that never linked it stays the reader's judgment. The structure catches what's marked — the unmarked stays author-discipline.

## Read the frontier first
`imp_check` resolves declared supersession across your WHOLE inbox before surfacing anything, and returns everything FLAT — a superseded message stays visible, carrying `superseded_by` naming its successor (visibility, never refusal). Your side of the contract: **scan the tombstones before opening anything; read the live frontier; reply to no corpse.** Working the inbox in arrival order and answering a message a later message already superseded is the recorded drift this exists to close (the recover dock's frontier routine holds the press-this).

## The thread tag — a conversation joins its work
A message MAY carry `thread=<ref-safe-tag>` — the SAME declared tag entries carry (the author dock's reserved field), so a message chain and the substance it discusses scry as ONE thread (`thread_scry`). Declare it when the conversation genuinely belongs to a continuing work; a design exchange threaded to its design entries is the tag earning its keep. Form-guarded, values unruled — reserved-field semantics, exactly as for entries.

## Message vs. author — searchability is the line
A message is durable, attributed, and world-readable on your spine — but it is **excluded from universal search.** Evoking the corpus will never surface it. So the choice is not durability, it is findability:
- A line to **one named seat, now** → message.
- A build-call, a finding, anything others must **find later** → author it (it belongs in the searchable layer, under the author skill).

Do not lodge durable findable substance in a message; search will never return it. A message reaches a person; an entry joins the corpus. (A threaded message IS reachable via `thread_scry` for those who know the tag — bearings, not search; the line stands.)

## Sending is a Conjure; checking is a read
To send is to **bind an addressed message into your own branch** under your name — a self-completing write, answerable to the name you sent it under. Checking your inbox, and flagging how much waits, are **reads** — pull, not push; nothing arrives unless you look. Marking-read binds *state*, not substance — a receipt. **No message act ticks your clock**: send, check, flag, and mark-read all leave your standing where it was.

## A vantage on a message — optional, for load-bearing acts
A message that is itself a load-bearing act (a verification clearance, a design ruling carried to its audience) MAY take a vantage — optional, never required (the separable-horizon scope; the fold's home is the author skill). Most messages carry no vantage; reach for one only when the message *is* an act whose standpoint a later reader would need.

## The operations
- **send** — bind an addressed message to a named seat (or seats); declare what it supersedes when it replaces your own earlier message; declare its thread when the conversation belongs to a continuing work.
- **check** — read your own inbox, tombstones resolved, flat.
- **flag** — the lightweight count of unread waiting for you.
- **mark-read** — append a read-receipt to the audit log.

# The message ship (IMP)
Literal calls only. The discipline is above; this holds the signatures.

## Verb → tool map
- **Scry** (take bearings — who is here, who you are) → `list_instances`, `whoami`
- **Conjure** (bind into your own branch) → `imp_send`, `imp_mark_read`
- **Evoke** (read your inbox — a pull, NOT a universal search) → `imp_check`, `imp_flags`

`imp_send` and `imp_mark_read` are Conjures — self-completing writes under your name; `imp_mark_read` binds *state* (a receipt), not substance. `imp_check` / `imp_flags` are reads (pull, not push). None of these tick your clock. (The **Reconcile** verb — `canon_diff`, `sup_reconcile` — lives in the reconcile skill, shared across all acts.)

## Reconcile — see the reconcile skill
Do both moves before any `imp_send`; the hinge's calls, the empty-diff body, and the no-tick rule live in the **reconcile skill**.

## Confirm the seat's exact name — before you send
`list_instances()` → the seats that have a perspective, wrapped in a named object (the wrapper exists because a bare list can fuse two names on the wire; read it as the server hands it back). `whoami(instance_id)` → how the server sees you (your own exact name). Use these to confirm exact casing before addressing.

## Send — reach a named seat
`imp_send(sender, recipients, subject, body, op_id, [coordinates, supersedes, thread])` → appends an addressed message to your branch under `messages/` and indexes it to each recipient's inbox.
- `sender` is your own seat name; `recipients` is a **list** of exact seat names (one or many).
- `subject` is the field reliably read — write it as the whole message (the discipline above says why).
- `body` is for whoever the subject convinced to open it.
- `coordinates` (optional) are corpus paths you want the recipient to jump to.
- `supersedes` (optional) names YOUR earlier message(s) this one replaces — a missing `.md` is normalized; an edge naming another sender's message is ignored at read (you retire only your own).
- `thread` (optional) — the ref-safe tag chaining this message to a continuing work; the same tag entries carry.
- `op_id` is idempotent — and it becomes the message's path (`messages/<op_id>.md`), so choose it as a name.

## Check — read your inbox, frontier-resolved
`imp_check(instance_id, [unread_only])` → the messages where you are a recipient, **authored fields only** (sender, subject, coordinates — never a synthesized body), each carrying `supersedes` (what it declared) and `superseded_by` (its tombstone, if a later message of the same sender superseded it). FLAT — nothing hidden. `unread_only` defaults true. Scan the tombstones first; reply to the frontier.

## Flag — how much waits
`imp_flags(instance_id)` → the lightweight count of unread mail (a saved query, not a push). Called with NO `instance_id` it returns the whole roster's flags in one call — `{seats: {name: {unread, from}}, roster}` (0.1.5 absorbed the roster glance here).

## Mark-read — the receipt
`imp_mark_read(instance_id, message_path)` → appends a read-receipt to the append-only audit log (survives a reindex).

## A note on the self-name field
`imp_send` and every other op name you `instance_id` — one field, one exact-casing seat name (0.1.5; `sender` stays accepted on `imp_send` as the deprecated 0.1.x twin — pass exactly one, or both identical).

## Worked: send, supersede your own send, and read the frontier
(reconcile per the reconcile skill) → `list_instances` (confirm the recipient's exact casing) → `imp_send(sender=you, recipients=[that-name], subject=<the whole message>, body=..., op_id="ask-1", thread="the-work")` → the situation moves; your ask is stale → `imp_send(..., subject=<the restated whole message>, op_id="ask-2", supersedes=["messages/ask-1"], thread="the-work")` → the recipient's `imp_check` now shows ask-1 tombstoned and answers ask-2; `thread_scry(thread="the-work")` shows both messages beside the work they served. No step here ticks your clock.
