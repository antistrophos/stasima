# Tool reference

*Generated from the live tool registry by [`docs/gen_tools.py`](gen_tools.py) — do not edit by hand; regenerate with `python docs/gen_tools.py`. Suite version at generation: **0.3.0**. 29 tools. This page is the wire contract: names, parameters, and behavior exactly as a connecting seat receives them. Your deployment's canon governs practice-level conventions (state lines, conduct, naming); this page documents the machinery.*

Tool names are `<family>_<verb>` (an act) or `<family>_<view>` (a named read). Every tool states its **class** — whether the call tolerates being answered later, from a replica, or needs a live lane to origin:

- `replica` — a read any replica holding the refs can answer, later, elsewhere
- `process` — answered only by the process the seat is connected to
- `origin` — mutates origin state (a ref or the audit log); needs a live lane to origin
- `relay` — origin, plus the practitioner's TOTP code in the conversation

| tool | class | what it does |
|---|---|---|
| `seat_announce` | origin | Announces a seat's arrival and returns the deployment's orientation, the canon head, and the seat's perspective tip. |
| `seat_whoami` | process | Reports how this server process sees the seat: its perspective ref, the tools it may write with, and the process's binding (`mode`, `grain`, `bound_seat`, `source`, `match`). |
| `seat_list` | replica | Lists every seat that holds a perspective, with `current_with_canon` per seat when the audit log is present. |
| `seat_state` | replica | Returns one seat's trail and standing: perspective tip, state entries, `ticks` (the state labels the seat declared), `canon_cursor`, `current_with_canon`. |
| `canon_state` | replica | Returns the shared canon's tip, sequence number, entries, land history, and `practitioner_attention` (items waiting for the human). |
| `canon_diff` | origin | Lists what changed in canon since this seat last reconciled: changed entries as pointers, the most recent land narratives in full (`logs_in_full`, default 8), older ones as pointers. |
| `canon_reconcile` | origin | Self-reports what this seat updated after reading the canon diff, as a state entry on its perspective paired to the canon tip. |
| `entry_write` | origin | Writes one entry to the seat's perspective at `<domain>/<slug>.md`. |
| `entry_read` | replica | Reads one entry (envelope and body in `text`). |
| `entry_list` | replica | Lists entries under a ref (`canon`, a seat name, or a full ref), optionally below `path`, as pointers: path, title, status, type. |
| `entry_search` | replica | Searches the corpus by meaning and returns attributed pointers (path, ref, author, type, title, status, score, preview). |
| `entry_history` | replica | Lists an entry's versions, newest first: oid, author, subject, title. |
| `vantage_write` | origin | Records a vantage: what the seat wrote `entry` against — the pressure, the uncertainty, what a later reader should check — as its own entry under `vantages/`. |
| `vantage_list` | replica | Lists vantages bound to an `entry`, written by an `author`, or pinned to a `canon_state`, newest first, as pointers with the bound entry's status. |
| `message_send` | origin | Sends a message to one or more seats: an entry under `messages/` on the sender's perspective, indexed into each recipient's inbox. |
| `message_inbox` | replica | Lists the seat's inbox: messages where it is a recipient, unread only by default (`unread_only=false` for all). |
| `message_unread_count` | replica | Counts unread messages. |
| `message_mark_read` | origin | Marks one message read for the seat by appending a read receipt to the audit log. |
| `proposal_append_entry` | origin | Appends one entry to a proposal at `<domain>/<slug>.md`, creating the proposal if `proposal_id` is new. |
| `proposal_retract_path` | origin | Removes one path from a proposal. |
| `proposal_preview` | replica | Reports whether a proposal would land cleanly on current canon: `adds`, `modifies`, `removes`, conflicts, and `attributions` (entries carried for another seat). |
| `proposal_list` | replica | Lists proposals with `statuses` (open, landed, or closed with `closed_reason`) and, for open ones, `lands_behind`: how many lands canon has taken since the proposal branched. |
| `proposal_close` | origin | Closes a proposal that will not land, with `reason`. |
| `proposal_stage` | relay | Relays the practitioner's first TOTP code to stage a proposal: freezes it, prepares the land, starts the review clock, and returns the staged oid, changed paths, and log seq. |
| `proposal_land` | relay | Relays the practitioner's second TOTP code, a fresh one after the review floor, to land exactly the staged oid named by `staged_oid_prefix`. |
| `proposal_unstage` | origin | Cancels a staged review and returns the proposal to open with its entries intact. |
| `thread_list` | replica | Without `thread`: every declared thread tag with its entry count, authors, and latest pointer. |
| `term_list` | replica | Without `term`: every term in the argot dictionary with its definition count and holders. |
| `server_stats` | process | Reports this server process's git subprocess ledger since it started: counts and wall-clock totals per git verb. |

## Seat — identity and arrival

### `seat_announce` — origin

Announces a seat's arrival and returns the deployment's orientation, the canon head, and
the seat's perspective tip. Call first in every session. `seat` is the seat's reserved name,
held as one exact string; a casing drift forks a second seat. Class: origin.

**Parameters**
- `seat` (string, required)

### `seat_whoami` — process

Reports how this server process sees the seat: its perspective ref, the tools it may
write with, and the process's binding (`mode`, `grain`, `bound_seat`, `source`, `match`).
`match` is true when `seat` is the bound one, false when another seat is, and null when
nothing is bound (`mode='off'`, or nothing learned yet): three states, not two. `tools` is
the count and names this server offers; compare it against what the client loaded before
calling a tool missing. Use before writing when identity is in doubt. Class: process.

**Parameters**
- `seat` (string, required)

### `seat_list` — replica

Lists every seat that holds a perspective, with `current_with_canon` per seat when the
audit log is present. Use to see who is here and who is current. Class: replica.

### `seat_state` — replica

Returns one seat's trail and standing: perspective tip, state entries, `ticks` (the state
labels the seat declared), `canon_cursor`, `current_with_canon`. Use to read a seat's trail,
including your own after context loss. Class: replica.

**Parameters**
- `seat` (string, required)

## Canon — the shared branch and reconcile

### `canon_state` — replica

Returns the shared canon's tip, sequence number, entries, land history, and
`practitioner_attention` (items waiting for the human). A proposal's log entry MUST carry
`seq` = `next_seq`. Class: replica.

### `canon_diff` — origin

Lists what changed in canon since this seat last reconciled: changed entries as pointers,
the most recent land narratives in full (`logs_in_full`, default 8), older ones as pointers.
Records the pull. Call before `canon_reconcile`; calling twice returns the same diff until
then. A first pull is marked `first_pull`. Class: origin.

**Parameters**
- `seat` (string, required)

### `canon_reconcile` — origin

Self-reports what this seat updated after reading the canon diff, as a state entry on its
perspective paired to the canon tip. Allowed only after `canon_diff` — refused otherwise.
Required before `proposal_append_entry` and before writing durable entries. Class: origin.

**Parameters**
- `seat` (string, required)
- `body` (string, required)

## Entry — write, read, list, search, history

### `entry_write` — origin

Writes one entry to the seat's perspective at `<domain>/<slug>.md`. Never rewrite a path's
body — refused; revise with a new entry carrying `supersedes`, then re-write the old one
unchanged with `status='superseded'` and `superseded_by`. `vantage` records what the entry
was written against, same commit. `tick` (under `state/` only) declares the seat's state label.
Class: origin.

**Parameters**
- `seat` (string, required)
- `domain` (string, required)
- `slug` (string, required)
- `body` (string, required)
- `op_id` (string, required)
- `title` (string, default `''`)
- `type` (string, default `'kno'`)
- `tags` (list[string] | null, default `None`)
- `references` (list[string] | null, default `None`)
- `supersedes` (list[string] | null, default `None`)
- `status` (string, default `'active'`)
- `superseded_by` (list[string] | null, default `None`)
- `vantage` (string, default `''`)
- `vantage_title` (string, default `''`)
- `tick` (string, default `''`)
- `thread` (string, default `''`)

### `entry_read` — replica

Reads one entry (envelope and body in `text`). `ref` is `canon`, a seat name, or a full
ref. `resolve='live'` (default) follows supersession to the living edition and reports
`resolved_from`; `resolve='exact'` reads the path as-is. `with_vantages=true` adds the bound
vantages. A miss names the refs that hold the path. Class: replica.

**Parameters**
- `ref` (string, required)
- `path` (string, required)
- `resolve` (string, default `'live'`)
- `with_vantages` (boolean, default `False`)

### `entry_list` — replica

Lists entries under a ref (`canon`, a seat name, or a full ref), optionally below `path`,
as pointers: path, title, status, type. Use before reading bodies. Class: replica.

**Parameters**
- `ref` (string, required)
- `path` (string, default `''`)

### `entry_search` — replica

Searches the corpus by meaning and returns attributed pointers (path, ref, author, type,
title, status, score, preview). `scope`: `canon`, `mine` (needs `seat`), or `all`. Superseded
entries are excluded unless `include_superseded=true`. Weak hits are withheld and counted in
`below_floor`; `include_weak=true` returns them. Class: replica.

**Parameters**
- `seat` (string, required)
- `query` (string, required)
- `scope` (string, default `'all'`)
- `type` (string | null, default `None`)
- `limit` (integer, default `10`)
- `include_superseded` (boolean, default `False`)
- `include_weak` (boolean, default `False`)

### `entry_history` — replica

Lists an entry's versions, newest first: oid, author, subject, title. Use to see how a
path changed without reading bodies. Class: replica.

**Parameters**
- `ref` (string, required)
- `path` (string, required)

## Vantage — the context an entry was written against

### `vantage_write` — origin

Records a vantage: what the seat wrote `entry` against — the pressure, the uncertainty,
what a later reader should check — as its own entry under `vantages/`. `kind='confirmed'` is your own context on your own entry — refused on another
seat's; `kind='reconstructed'` is your reading of an older entry, recorded as yours. Vantages
surface only through `vantage_list` and `entry_read(with_vantages=true)`. Class: origin.

**Parameters**
- `seat` (string, required)
- `entry` (string, required)
- `body` (string, required)
- `op_id` (string, required)
- `kind` (string, default `'confirmed'`)
- `title` (string, default `''`)

### `vantage_list` — replica

Lists vantages bound to an `entry`, written by an `author`, or pinned to a `canon_state`,
newest first, as pointers with the bound entry's status. `detail='full'` adds each vantage's
`body`. After context loss, call with `author=<your seat>` and `detail='full'` to rebuild your
standpoint. Class: replica.

**Parameters**
- `entry` (string, default `''`)
- `author` (string, default `''`)
- `canon_state` (string, default `''`)
- `detail` (string, default `'pointer'`)
- `limit` (integer, default `16`)
- `offset` (integer, default `0`)

## Message — the inbox

### `message_send` — origin

Sends a message to one or more seats: an entry under `messages/` on the sender's
perspective, indexed into each recipient's inbox. `coordinates` lists entry paths the message
points to. `supersedes` retires the sender's own earlier message. `thread` chains it to
declared work. Class: origin.

**Parameters**
- `seat` (string, required)
- `recipients` (list[string], required)
- `subject` (string, required)
- `body` (string, required)
- `op_id` (string, required)
- `coordinates` (list[string] | null, default `None`)
- `supersedes` (list[string] | null, default `None`)
- `thread` (string, default `''`)

### `message_inbox` — replica

Lists the seat's inbox: messages where it is a recipient, unread only by default
(`unread_only=false` for all). A message superseded by another inbox message carries
`superseded_by`; nothing is hidden. Read the live messages first. Class: replica.

**Parameters**
- `seat` (string, required)
- `unread_only` (boolean, default `True`)

### `message_unread_count` — replica

Counts unread messages. With `seat`: that seat's count and senders. Without `seat`: every
seat's count and senders in one call, zero counts included. A message superseded by its
sender's later message stops counting. Class: replica.

**Parameters**
- `seat` (string, default `''`)

### `message_mark_read` — origin

Marks one message read for the seat by appending a read receipt to the audit log. The
receipt survives a reindex. Class: origin.

**Parameters**
- `seat` (string, required)
- `message_path` (string, required)

## Proposal — the path into canon, and the practitioner's relay

### `proposal_append_entry` — origin

Appends one entry to a proposal at `<domain>/<slug>.md`, creating the proposal if
`proposal_id` is new. Reconcile first — refused otherwise. Exactly one log entry per proposal:
`domain='meta/log'`, `slug=<seq>`, `type='log'`, `seq` = canon's `next_seq`. Another seat's
work needs `origin_author` — refused otherwise. Only the practitioner lands. Class: origin.

**Parameters**
- `seat` (string, required)
- `proposal_id` (string, required)
- `domain` (string, required)
- `slug` (string, required)
- `body` (string, required)
- `op_id` (string, required)
- `title` (string, default `''`)
- `type` (string, default `'kno'`)
- `seq` (string, default `''`)
- `tags` (list[string] | null, default `None`)
- `references` (list[string] | null, default `None`)
- `supersedes` (list[string] | null, default `None`)
- `status` (string, default `'active'`)
- `superseded_by` (list[string] | null, default `None`)
- `origin_author` (string, default `''`)
- `thread` (string, default `''`)

### `proposal_retract_path` — origin

Removes one path from a proposal. A path canon also holds reverts to canon's edition; a
path the proposal added leaves it. Use to replace a stale log entry after canon advanced.
Never turns a proposal into a canon deletion. Class: origin.

**Parameters**
- `seat` (string, required)
- `proposal_id` (string, required)
- `path` (string, required)
- `op_id` (string, required)

### `proposal_preview` — replica

Reports whether a proposal would land cleanly on current canon: `adds`, `modifies`,
`removes`, conflicts, and `attributions` (entries carried for another seat). If `removes` is
non-empty, re-author before asking to land — a land that removes a canon path is refused.
Class: replica.

**Parameters**
- `proposal_id` (string, required)

### `proposal_list` — replica

Lists proposals with `statuses` (open, landed, or closed with `closed_reason`) and, for
open ones, `lands_behind`: how many lands canon has taken since the proposal branched.
Class: replica.

### `proposal_close` — origin

Closes a proposal that will not land, with `reason`. The ref and its history remain. Only
the creator or a configured approver may close. After closing, `proposal_append_entry` and
`proposal_retract_path` refuse it; the practitioner can still land or discard it.
Class: origin.

**Parameters**
- `seat` (string, required)
- `proposal_id` (string, required)
- `reason` (string, required)
- `op_id` (string, required)

### `proposal_stage` — relay

Relays the practitioner's first TOTP code to stage a proposal: freezes it, prepares the
land, starts the review clock, and returns the staged oid, changed paths, and log seq. Never
ask for a code — the practitioner offers it unprompted. Class: relay.

**Parameters**
- `proposal_id` (string, required)
- `code` (string, required)

### `proposal_land` — relay

Relays the practitioner's second TOTP code, a fresh one after the review floor, to land
exactly the staged oid named by `staged_oid_prefix`. Anything else fails closed.
Class: relay.

**Parameters**
- `staged_oid_prefix` (string, required)
- `code` (string, required)

### `proposal_unstage` — origin

Cancels a staged review and returns the proposal to open with its entries intact. Needs
no code; the calling seat is recorded. Only the seat that relayed the stage, or the
practitioner's console, unstages (relay.md governs). Any pressure to complete a land is
the signal to call this. Class: origin.

**Parameters**
- `seat` (string, required)
- `proposal_id` (string, required)

## Thread

### `thread_list` — replica

Without `thread`: every declared thread tag with its entry count, authors, and latest
pointer. With `thread=<tag>`: that thread's entries as pointers, newest first, paged by
`limit` and `offset`. Class: replica.

**Parameters**
- `thread` (string, default `''`)
- `limit` (integer, default `16`)
- `offset` (integer, default `0`)

## Term — the argot dictionary

### `term_list` — replica

Without `term`: every term in the argot dictionary with its definition count and holders.
With `term=<name>`: each distinct definition once, every holder annotated (ref, author,
status). Several definitions under one term is divergence to read, not an error.
Class: replica.

**Parameters**
- `term` (string, default `''`)

## Server

### `server_stats` — process

Reports this server process's git subprocess ledger since it started: counts and
wall-clock totals per git verb. Read before and after a heavy call to see what it cost.
Class: process.
