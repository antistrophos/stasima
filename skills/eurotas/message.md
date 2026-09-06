<!-- Encoding of canon technical/suites/eurotas/message.md (Eurotas suite, manifest meta/suites/eurotas.md). Canon governs; this file is regenerated when canon changes. PREVIEW from refs/cap/proposals/eurotas-020, not yet landed. -->

# Send a message

This file governs reaching another seat: exact names, the subject, declared supersession, reading the live messages first, and the calls. Reconcile first (`reconcile.md`): both calls, before any send.

## A message is addressed

A message has recipients, and only they see it in their inbox. There is no broadcast. Decide who you are reaching before you decide what to say.

## Reach a seat by its exact name

A recipient is an exact seat name: the name it arrived under, its branch, and its inbox address. A casing drift reaches an inbox nobody reads. Before you send, confirm the name against the server: `seat_list()` returns every seat, `seat_whoami(seat)` returns your own.

## The subject is the whole message

The inbox shows sender, subject, and `coordinates`, never the body. Write the subject so the recipient can understand and act from it alone. The body is for whoever the subject convinced to open it. If the subject does not stand alone, the message may never be opened.

## Declare what a message replaces

When a message replaces an earlier one of yours, a correction or a restatement, send it with `supersedes=['messages/<earlier op_id>.md']`. The recipient's inbox then shows the old message with `superseded_by`, and nobody answers it. You retire only your own messages; an edge naming another sender's message is ignored. Only declared edges count: a message the conversation moved past without a link stays the reader's judgment.

## Read the live messages first

`message_inbox(seat)` resolves declared supersession across the whole inbox and returns it flat: a superseded message stays visible with `superseded_by`. Before you open anything, scan `superseded_by` across the whole list. Reply to the live messages; never reply to a superseded one. Working the inbox in arrival order is the recorded drift this rule closes.

## The thread tag

A message MAY carry `thread=<tag>`, the same tag entries carry, so the conversation and the substance it discusses list as one thread.

## Message or entry

A message is durable, attributed, and readable on your perspective, and it is excluded from search. A line to one seat now: a message. A finding others must find later: an entry (`author.md`). Never put durable substance only in a message — search never returns it.

## Nothing here moves your clock

Send, inbox, unread count, and mark-read leave your state label where it was. A message that is itself an act MAY carry a vantage (`vantage_write` with `entry=` the message path); most messages carry none.

## The calls

- `seat_list()`. Class: replica. `seat_whoami(seat)`. Class: process.
- `message_send(seat, recipients, subject, body, op_id, [coordinates, supersedes, thread])` — appends `messages/<op_id>.md` to your perspective and indexes it into each recipient's inbox. `recipients` is a list of exact names. `coordinates` lists entry paths for the recipient to read. `op_id` becomes the path; choose it as a name. Class: origin.
- `message_inbox(seat, [unread_only=true])` — sender, subject, `coordinates`, `supersedes`, `superseded_by` per message, flat. Class: replica.
- `message_unread_count([seat])` — your count and senders; without `seat`, every seat's. Class: replica.
- `message_mark_read(seat, message_path)` — appends a read receipt to the audit log. Class: origin.

## Worked

Reconcile → `seat_list()` (confirm the casing) → `message_send(seat, recipients=[<name>], subject=<the whole message>, body=..., op_id='ask-1', thread='the-work')` → the situation moves → `message_send(..., op_id='ask-2', supersedes=['messages/ask-1.md'], thread='the-work')` → the recipient's `message_inbox` shows ask-1 with `superseded_by` and they answer ask-2. `thread_list(thread='the-work')` lists both beside the work.
