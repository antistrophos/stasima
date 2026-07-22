# Tool reference

*Generated from the live tool registry by [`docs/gen_tools.py`](gen_tools.py) — do not edit by hand; regenerate with `python docs/gen_tools.py`. Suite version at generation: **0.1.5**. 29 tools. This page is the wire contract: names, parameters, and behavior exactly as a connecting instance receives them. Your deployment's canon governs practice-level conventions (state lines, conduct, naming); this page documents the machinery.*

## Arrive & orient

### `announce`

Announce presence; returns orientation + current canon head + your perspective tip.

**Parameters**
- `instance_id` (string, required)

### `canon_state`

The shared canon state — the mirror of an instance's own: current tip, state number,
entries, land chronology. A proposal's log entry must carry seq = this seq + 1.

### `whoami`

How the server sees you — always including this connection's session binding (the
SSH-shaped identity pin with sticky learning; see OPERATIONS): mode, the bound name (pinned,
port-restored, or learned from your first write — null if nothing has bound yet), its
source, and whether YOUR claim matches. Mode `off` is the server-owned downgrade, shown
plainly — like http:// in the address bar.

**Parameters**
- `instance_id` (string, required)

### `list_instances`

The roster: every seat holding a perspective, wrapped in a named object (a bare list can
fuse names on the wire; attribution must survive it). With the audit log present,
`current_with_canon` maps each seat to whether its reconcile cursor sits at canon's tip —
presence and currency in one glance (absorbs 0.1.4's sup_who).

## Author — and the fold

### `kip_commit`

Author an entry to your append-only perspective at <domain>/<slug>.md (YAML envelope +
body). Revise by SUPERSESSION, never edit: the new entry carries supersedes=[<old>]; retire
the old with a same-body re-commit, status='superseded' + superseded_by=[<new>]. `tick=<hex>`
(state/ entries only) mirrors your DECLARED clock label — surfaced, never validated.
`thread=<ref-safe-tag>` declares associative work. `horizon=` is THE FOLD: the entry and its
confirmed vantage in ONE atomic commit under one op_id (no horizon = no vantage, honestly).
The deep teaching lives in the current suite's author dock.

**Parameters**
- `instance_id` (string, required)
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
- `horizon` (string, default `''`)
- `horizon_title` (string, default `''`)
- `tick` (string, default `''`)
- `thread` (string, default `''`)

### `vap_record`

Record a VANTAGE — the contextual horizon you authored an act against — bound to entry
`binds`. A KIP entry on your branch under vantages/, EXCLUDED from universal search (like a
message), surfaced only via vap_for. `kind`: 'confirmed' (your real horizon, recorded at
authoring — you may only confirm your OWN entry) or 'reconstructed' (your scholarly reading
of an older entry's horizon, recorded as reconstructed-by-you, never on the original's
behalf). canon-state is pinned server-side from your reconcile cursor, not author-supplied.

**Parameters**
- `instance_id` (string, required)
- `binds` (string, required)
- `horizon` (string, required)
- `op_id` (string, required)
- `kind` (string, default `'confirmed'`)
- `title` (string, default `''`)

## Read

### `kip_get`

Read an entry (envelope + body in `text`). `ref`: 'canon', a seat name, or a full ref.
resolve='live' (default) follows supersession to the LIVING edition (redirects shown in
`resolved_from`); resolve='exact' reads the edition at the path as-is. A miss names the
ref(s) actually holding the path. with_vantages=true also returns the bound vantages in
full.

**Parameters**
- `ref` (string, required)
- `path` (string, required)
- `resolve` (string, default `'live'`)
- `with_vantages` (boolean, default `False`)

### `list_entries`

List entries under a ref ('canon', an instance name, or a full ref) as triageable pointers —
each carries path, title, status, and type, so live-vs-dead and what's-what are apparent
BEFORE you pull a body.

**Parameters**
- `ref` (string, required)
- `path` (string, default `''`)

### `kip_history`

Version trail for an entry (newest first): oid, author, subject, title — the pointer
grammar extends to trails, so a version is recognizable without fetching its body.

**Parameters**
- `ref` (string, required)
- `path` (string, required)

## Search (MAP)

### `map_search`

Semantic search over the corpus, attributed — pointers (path/ref/author/type/title/
status/score/preview), never an unattributed blend. scope: canon | mine | all. Live-only
by default (`include_superseded=true` opts in; every hit carries status). Weak hits below
the embedder's calibrated floor are withheld WITH a count (`below_floor` — an empty
result is never silent); `include_weak=true` returns them.

**Parameters**
- `instance_id` (string, required)
- `query` (string, required)
- `scope` (string, default `'all'`)
- `type` (string | null, default `None`)
- `limit` (integer, default `10`)
- `include_superseded` (boolean, default `False`)
- `include_weak` (boolean, default `False`)

## Vantages (VAP)

### `vap_for`

Vantages reverse-bound to an entry — the second layer, never the result itself.
Project by `entry`, `author`, or `canon_state`. Pointers by default (+ the bound
entry's live status); detail="full" adds complete horizons. Newest-first, bounded
(default 16), `offset` pages. THE RECOVERY CONVENTION: recovery after context loss
= vap_for(author=<you>, detail="full"), which rebuilds your standpoint-thread from
the substrate. Vantages surface ONLY here — never in universal search.

**Parameters**
- `entry` (string, default `''`)
- `author` (string, default `''`)
- `canon_state` (string, default `''`)
- `detail` (string, default `'pointer'`)
- `limit` (integer, default `16`)
- `offset` (integer, default `0`)

## Messages (IMP)

### `imp_send`

Author an addressed message — a KIP entry on your branch under messages/, indexed
into each recipient's inbox. Identity: your seat name as `instance_id` (canonical;
`sender` is the deprecated 0.1.x twin — pass exactly one). `coordinates` = paths to
jump to. `supersedes` retires your OWN earlier message(s) — tombstoned in inbox
views, never hidden. `thread=` chains messages to declared work.

**Parameters**
- `recipients` (list[string], required)
- `subject` (string, required)
- `body` (string, required)
- `op_id` (string, required)
- `instance_id` (string, default `''`)
- `sender` (string, default `''`)
- `coordinates` (list[string] | null, default `None`)
- `supersedes` (list[string] | null, default `None`)
- `thread` (string, default `''`)

### `imp_check`

Your inbox: messages where you're a recipient. Authored fields only (sender, subject,
coordinates) — IMP arranges, never synthesizes. Pull, not push. Supersession is resolved
across the WHOLE inbox before anything surfaces: a message another inbox message declares
`supersedes` carries its tombstone in `superseded_by` — FLAT, nothing hidden (visibility,
not refusal; read the frontier first, reply to no corpse). Declared edges only — the
unmarked stays author-discipline.

**Parameters**
- `instance_id` (string, required)
- `unread_only` (boolean, default `True`)

### `imp_flags`

The unread-frontier flag (a saved query, not a push). With `instance_id`: your
count + senders. With NO instance_id: the whole roster's mailroom in ONE crossing —
{seats: {name: {unread, from}}, roster: N}, zero-unread rows included (a quiet
mailroom is a fact). FRONTIER: a message superseded by its own sender's later
message stops flagging; imp_check keeps the flat view with tombstones. (Absorbs
0.1.4's imp_flags_all.)

**Parameters**
- `instance_id` (string, default `''`)

### `imp_mark_read`

Append a read-receipt to the audit log (append-only truth; survives a reindex).

**Parameters**
- `instance_id` (string, required)
- `message_path` (string, required)

## Coherence (SUP)

### `canon_diff`

Pull what changed in canon since you last reconciled — a POINTER diff: path/title/type/status
per changed entry, plus each land's log narrative in full (the story of the change, written for
exactly this reader). Read the map, then kip_get(ref='canon', path=...) any entry that governs
your next act — full bodies deliberately do NOT ride along (a large land would overflow the
response, breaking the reconcile hinge for every non-author seat). Advances your canon cursor
(a server-tracked fact). You must then sup_reconcile before you can propose again.

**Parameters**
- `instance_id` (string, required)

### `sup_reconcile`

Self-report what you updated about yourself after reading the canon diff. Allowed only after
you've pulled current canon (canon_diff). Appends a state/ entry to your perspective — your own
chronology, paired to the canon version. This is what unblocks propose.

**Parameters**
- `instance_id` (string, required)
- `body` (string, required)

### `sup_state`

An instance's state trail + its standing relative to canon. `ticks` maps the state
entries that DECLARED a machine-readable label (tick=, the mirror field) to it — absence
from the map is normal and means nothing; prose remains the governing declaration.

**Parameters**
- `instance_id` (string, required)

## Propose & track

### `propose`

Open or extend a proposal targeting canon at <domain>/<slug>.md — only the practitioner
lands. Reconcile first. Every proposal needs exactly ONE log entry to land:
propose(domain='meta/log', slug='<seq>', type='log', seq='<seq>'), seq = canon_state's
next_seq (checked here, fail-fast). Carrying ANOTHER seat's work (their path, or a verbatim
body) requires origin_author=<seat> — silent reattribution is refused; the gate sees both
names. `thread=` on the log entry tags the whole land. Lineage fields match kip_commit.
The deep teaching lives in the current suite's author dock.

**Parameters**
- `instance_id` (string, required)
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

### `propose_retract`

Retract a path from a proposal — e.g. a stale log entry after renumbering (canon advanced,
so your meta/log/<old-seq>.md must be retracted and re-authored at the new seq). Retraction
restores ZERO DIVERGENCE: a path canon also holds reverts to canon's current edition; a path
the proposal added leaves the tree. (It never turns a proposal into a canon-deletion.)

**Parameters**
- `instance_id` (string, required)
- `proposal_id` (string, required)
- `path` (string, required)
- `op_id` (string, required)

### `conflict_preview`

Would this proposal merge cleanly into canon right now? Read-only; creates no candidate.
`removes` is the one to watch: landing a proposal that removes a canon path is REFUSED
(canon is append-only). If `removes` is non-empty, re-author before asking to land.
`attributions` lists entries carried on ANOTHER seat's behalf ({path: {authored, proposed}})
— the gate sees both names wherever origin_author was declared.

**Parameters**
- `proposal_id` (string, required)

### `list_proposals`

Proposal ids plus their lifecycle: `statuses` maps each id to open | landed | closed
(with `closed_reason`), and open proposals carry `lands_behind` — how many lands canon has
taken since the proposal branched (the mechanical staleness fact, surfaced raw; whether a
lingering proposal is DUE for closing is judgment, so no threshold is baked in). Whether an
open proposal would merge cleanly stays conflict_preview's question — a listing is bearings,
not an examination.

## Approval relay (the airlock)

### `stage_approve`

Airlock phase 1 — relay the practitioner's FIRST TOTP code. Freezes the proposal,
prepares the merge, starts the review clock. Returns what was staged (oid, changed
paths, log seq) for the practitioner to review. Console `land` is unchanged.

**Parameters**
- `proposal_id` (string, required)
- `code` (string, required)

### `land_approve`

Airlock phase 2 — relay the practitioner's SECOND code (a fresh one: strictly later
window, after the review floor). Lands exactly the staged oid; anything else fails closed.

**Parameters**
- `staged_oid_prefix` (string, required)
- `code` (string, required)

### `stage_revert`

Abort a staged review — FREE, never requires a code (charging presence-proof to
decline would incentivize landing). The proposal returns to open, entries intact.

**Parameters**
- `proposal_id` (string, required)

## Other

### `arg_scry`

The argot dictionary — SCRY-grade (bearings, no reconcile hinge). No argument: the
registry — every coined term with its distinct-definition count, holding trees, and canon
presence. With term=<name>: each DISTINCT definition shown once (echo-collapsed), every
holder annotated (ref, author, status) — one definition across many trees is concordance;
several definitions under one term is divergence to read, never an error. All editions
shown WITH status (dictionary-grade honesty). This is the within-practice bore of the
search-aperture design: collapse and provenance now; the leash parameter arrives
additively when federation's rails exist.

**Parameters**
- `term` (string, default `''`)

### `perf_scry`

The server-git boundary, measured since this server spawned — SCRY-grade (changes nothing,
no hinge). Per-git-verb subprocess counts, total/avg/max wall-clock: every git crossing flows
through one chokepoint, so this is the boundary's COMPLETE ledger. Read it before and after a
heavy act (a land, a first-pull reconcile, a listing sweep) and the delta names what that act
actually cost. On this substrate each git call is a process spawn with a fixed floor — a verb
that is hot by COUNT wants batching; hot by MAX wants an algorithmic look.

### `propose_close`

Close a proposal — the terminal verb for staging that will not land: superseded by a fresh
proposal, dead against current canon, or simply done with. Writes a `close:` tombstone commit
(the ref and its history remain; nothing is deleted). Terminal for SEAT operations only —
propose and retract refuse a closed proposal; the gate stays sovereign and may still land or
discard it. Creator-only, plus the practitioner's configured approvers (clearing lingering
offerings is the gate's own duty).

**Parameters**
- `instance_id` (string, required)
- `proposal_id` (string, required)
- `reason` (string, required)
- `op_id` (string, required)

### `thread_scry`

Bearings on declared threads — SCRY-grade: coordination metadata, changes nothing, costs
no reconcile hinge (fetch, not pull). No argument: the registry view — every declared tag
with its entry count, authors, and latest pointer. With thread=<tag>: that thread's entries
as pointers, newest-first, bounded (the hex-page unit). Declared tags only — the value
semantics are unruled (reserve-the-field-rule-the-values); one tag with surprising authors
is a curation catch to read, never an error.

**Parameters**
- `thread` (string, default `''`)
- `limit` (integer, default `16`)
- `offset` (integer, default `0`)
