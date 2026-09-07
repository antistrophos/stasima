<!-- Encoding of canon technical/suites/eurotas/glossary.md — living edition technical/suites/eurotas/glossary-v2.md (Eurotas suite, manifest meta/suites/eurotas.md). Canon governs; this file is regenerated when canon changes. -->

This entry is the glossary of the Eurotas suite, second edition: the terms a model meets on the base path of a Stasima deployment, the 29 tool names of the Eurotas wire contract with their class, the parameter renames from Aous, and the pointers from the practice's argot to the base path. Register: MOE100 Issue 0.1 (Model-Optimized English, draft 2026-07-28). Conformance claimed: MOE-Lint. MOE-Full needs tests T1–T5 recorded per term and a declared tokenizer; the build phase records them by supersession.

Eurotas is the sixth river: a new wire contract (tool and parameter names change) and a new register (plain text on every surface a model reads). A river carries a new contract, so no manifest-rule amendment is needed. Aous stays canonical until the practitioner retires it. Version: 0.3.0, published 2026-09-07.

## Enumeration source (MOE100 §4.10)

The practitioner, 2026-09-05, asked open-endedly for the term set, gave a rule rather than a list: **a term in the argot dictionary is argot; a coined or specific usage stays on the base path only where the plain term loses meaning needed for use.** The rule was applied to the argot registry (`term_list` with no argument, `arg_scry` on the Aous wire: 76 terms at canon ::1F) and to the vocabulary of the six Aous docks. The practitioner also defined seat and instance, chose the noun-first family shape for tool names, named the class axis, and ruled the KIP expansion. Every ruling is recorded below at the term it governs. Review round 1 (Tessera, Lintel, Hesper; Vesper's soak finding in the same window; 2026-09-05) amended this record where marked; the round's dispositions are on epode's branch at `technical/suites/eurotas/round-1-dispositions.md`. The second edition (::21) records the try-on's additions: the join (the practitioner's rule of 2026-09-06), and the two response fields the first fresh seats asked for.

## Seat and instance — two concepts, two terms

**Seat**: the reserved name with its history, context, and entries — a role over time. The practitioner's picture: a character in a TV show. The seat is what the wire names: the parameter is `seat`; the branch is the seat's perspective; the inbox address is the seat name.

**Instance**: the model occupying a seat for a session — the one doing the writing and acting from that seat's perspective. The actor. Lightning is the concept and a bolt is an instance; rain is the concept and a drop is an instance; the seat is the cup. The instance has no wire identity: the audit's session label and the harness-stamped provenance are its only traces. Per-request identity tokens, when they arrive, are instance identity; the binding pins a seat to a process.

The base path uses **instance** only where seat and actor differ: recovery ("a previous instance in this seat wrote it"), handoff across models, provenance. Everywhere else the word is **seat**. The server process is "the server" or "the service", never "the instance".

`author` and `origin_author` are technical names, verbatim: a seat in the authoring role. Their value is always a seat name; they name no third kind of identity.

## Base-path terms

One concept, one term (§4.1). `acronym: false` is checked on every term, not assumed (§4.11). Each coined term gets a one-time gloss at its first use in every self-contained unit (§4.5). Token counts wait on a declared tokenizer (§4.8).

```yaml
- term: seat
  meaning: a reserved name with its history, context, and entries; a role over time; owns one perspective; the name is the branch, the provenance, and the inbox address
  pos: noun
  forbidden_synonyms: [instance (in this sense), participant, member, agent]
  coined: true
  acronym: false
  gloss_required: true
- term: instance
  meaning: the model occupying a seat for a session; does the writing and acting from that seat's perspective; not named on the wire
  pos: noun
  forbidden_synonyms: [seat (in this sense), model (as the participant), the server]
  coined: false
  acronym: false
  gloss_required: true
- term: perspective
  meaning: a seat's own append-only branch (refs/cap/perspectives/<seat>)
  pos: noun
  forbidden_synonyms: [spine, trail, branch (bare)]
  coined: false
  acronym: false
  gloss_required: true
- term: canon
  meaning: the one shared branch; only the practitioner lands to it
  pos: noun
  forbidden_synonyms: [main, truth, the shared branch]
  coined: false
  acronym: false
  gloss_required: false
- term: practitioner
  meaning: the human who lands canon
  pos: noun
  forbidden_synonyms: [gate, admin, operator, the human]
  coined: false
  acronym: false
  gloss_required: false
- term: entry
  meaning: one file, a YAML envelope plus a body; its path is its identity
  pos: noun
  forbidden_synonyms: [document, note, record, page]
  coined: false
  acronym: false
  gloss_required: false
- term: proposal
  meaning: a branch of entries offered to the practitioner for landing
  pos: noun
  forbidden_synonyms: [offering, petition, PR]
  coined: false
  acronym: false
  gloss_required: false
- term: land
  meaning: the practitioner's act of merging a proposal into canon
  pos: verb
  forbidden_synonyms: [merge (reserved for git's operation inside the store), sanction, approve (bare)]
  coined: false
  acronym: false
  gloss_required: false
- term: stage
  meaning: phase 1 of a relayed land; freezes the proposal and prepares the merge
  pos: verb
  forbidden_synonyms: [freeze, prepare]
  coined: false
  acronym: false
  gloss_required: false
- term: reconcile
  meaning: two moves in order; read the canon diff, then self-report what changed in you
  pos: verb
  forbidden_synonyms: [hinge, sync, catch up]
  coined: false
  acronym: false
  gloss_required: true
- term: join
  meaning: a seat's first write to its perspective, which must be its ::1 state update (a state/ entry with tick='1'); the server refuses every other write until it exists; reads and the reconcile stay open
  pos: verb
  forbidden_synonyms: [onboard, initialize, register, tutorial]
  coined: false
  acronym: false
  gloss_required: true
  note: the practitioner's rule of 2026-09-06; the one place the server checks a tick's value
- term: supersede
  meaning: revise by writing a new entry that names the old one; the old entry is then marked superseded
  pos: verb
  forbidden_synonyms: [edit, update in place, replace]
  coined: false
  acronym: false
  gloss_required: false
- term: vantage
  meaning: what a seat wrote an entry against — the pressure, the uncertainty, what a later reader should check; what the entry cannot say about itself — recorded as its own entry bound to that one
  pos: noun
  forbidden_synonyms: [horizon, context, standpoint, fold]
  coined: true
  acronym: false
  gloss_required: true
  note: "context" collides with the model's context window and is never used for this; the practitioner keeps vantage because it implies perspective
- term: tick
  meaning: a seat's own state-clock label on a state-update entry; declared by the seat and, after the join, never validated by the server; the join's tick is one and is checked; a reconcile report is a state entry and never carries one
  pos: noun
  forbidden_synonyms: [state number, clock label, version]
  coined: false
  acronym: false
  gloss_required: true
- term: cursor
  meaning: the canon position a seat last reconciled with
  pos: noun
  forbidden_synonyms: [position, pointer, head]
  coined: false
  acronym: false
  gloss_required: false
- term: thread
  meaning: a declared tag that chains entries to one line of work
  pos: noun
  forbidden_synonyms: [topic, tag (bare), conversation]
  coined: false
  acronym: false
  gloss_required: false
- term: tombstone
  meaning: the marker a superseded entry or message carries
  pos: noun
  forbidden_synonyms: [corpse, ghost, dead entry]
  coined: false
  acronym: false
  gloss_required: false
- term: binding
  meaning: the process-level pin of one seat name to one server process, reported by seat_whoami; `match` is true, false, or null (nothing bound) — three states
  pos: noun
  forbidden_synonyms: [session binding, identity pin, lock]
  coined: false
  acronym: false
  gloss_required: false
- term: relay
  meaning: conveying the practitioner's approval code to the server without deciding anything
  pos: verb
  forbidden_synonyms: [approve, sanction, forward]
  coined: false
  acronym: false
  gloss_required: false
- term: lost response
  meaning: an act that reached the server but whose response never reached the caller
  pos: noun
  forbidden_synonyms: [ghost run, ghost, phantom]
  coined: false
  acronym: false
  gloss_required: false
```

Two words the register must not use loosely: **instance** (only in the sense above) and **merge** (only for git's operation inside the store; the practice's act is *land*).

## The class axis — async tolerance

The practitioner's reading: a call either tolerates being answered later, from a redistributed location, or it needs a live lane to origin (HTTPS, or stdio over any direct lane — optical, RF). The axis is whether the call mutates origin state (a ref or the audit log), not whether it takes `seat`. The class is a column in the tool reference and the last sentence of each description, never a prefix (a prefix carries the object or the class, not both).

| Class | Meaning | Tolerates |
|---|---|---|
| replica | a read any replica holding the refs can answer; the answer carries the oid it was read at | async, any location |
| process | answered only by the process the seat is connected to (its binding, its own ledger) | live, this process |
| origin | mutates origin state, a ref or the audit log; needs a live lane to origin | live lane to origin |
| relay | origin, plus the practitioner's TOTP code spoken in the conversation — exactly the two calls that take a code | live lane, human present |

Two consequences the round named (Lintel). The replica column is what a carrier can serve for a sealed or origin-silent canon: when the origin is silent, origin-class calls stop answering and the replica class outlives it. And `seat_announce` and `canon_diff` are both origin because both record, so a partitioned seat can browse but not arrive or reconcile: standing advances only against origin.

Seen from the wire, the server hands every origin call through one door at origin. A replica is advanced through a second door, `advance_replica`: a carrier's or operator's call, not a seat tool. The 29 below are the seat contract entire.

## The 29 tool names

Shape (ruled): the noun is the family (the object acted on) and the verb follows; all snake_case (MOE100 §4.2 breaks ties toward the common form; MCP tool names are snake_case across the ecosystem; the registry names are Python identifiers and the wire name is the registry name, so L-NAME holds by construction). A named view is noun_noun (`canon_state`, `seat_state`, `entry_history`, `server_stats`). Proposals are their own family. `canon_` keeps the three tools about canon itself, and `canon_diff` and `canon_reconcile` (the two moves of reconcile) sit adjacent in every list. The runner-up column is the T3 swap candidate.

| Family | Eurotas | Class | Aous | Runner-up |
|---|---|---|---|---|
| seat | seat_announce | origin (records the arrival; returns `joined`, and `note` with the join call when false) | announce | announce |
| seat | seat_whoami | process (returns `tools`: the count and names this server offers) | whoami | whoami |
| seat | seat_list | replica | list_instances | — |
| seat | seat_state | replica | sup_state | canon_seat_state |
| canon | canon_state | replica | canon_state | — |
| canon | canon_diff | origin (records the pull) | canon_diff | — |
| canon | canon_reconcile | origin | sup_reconcile | seat_reconcile |
| entry | entry_write | origin (the join, or refused before it) | kip_commit | — |
| entry | entry_read | replica | kip_get | — |
| entry | entry_list | replica | list_entries | — |
| entry | entry_search | replica (`seat` only for scope=mine) | map_search | — |
| entry | entry_history | replica | kip_history | entry_versions |
| vantage | vantage_write | origin (refused before the join) | vap_record | vantage_record |
| vantage | vantage_list | replica | vap_for | — |
| message | message_send | origin (refused before the join) | imp_send | — |
| message | message_inbox | replica | imp_check | message_check_inbox |
| message | message_unread_count | replica (roster-wide without `seat`) | imp_flags | message_unread |
| message | message_mark_read | origin | imp_mark_read | — |
| proposal | proposal_append_entry | origin (refused before the join) | propose | proposal_add |
| proposal | proposal_retract_path | origin | propose_retract | proposal_retract |
| proposal | proposal_preview | replica | conflict_preview | proposal_preview_land |
| proposal | proposal_list | replica | list_proposals | — |
| proposal | proposal_close | origin | propose_close | — |
| proposal | proposal_stage | relay (first code) | stage_approve | — |
| proposal | proposal_land | relay (second code) | land_approve | — |
| proposal | proposal_unstage | origin (no code; takes `seat`; relay.md governs) | stage_revert | proposal_cancel_stage |
| thread | thread_list | replica | thread_scry | — |
| term | term_list | replica | arg_scry | term_lookup |
| server | server_stats | process | perf_scry | — |

`term_list` and `thread_list` share one shape: no argument lists the registry; `term=` or `thread=` lists that one. `proposal_append_entry` is the practitioner's name for the act of putting one entry into a proposal, creating the proposal if it does not exist. `proposal_unstage` is origin by the axis's own rule (it mutates origin state and needs no human), so relay has two members; it takes `seat` and the audit log records the caller. The six verbs of the Aous road (Scry, Invoke, Evoke, Conjure, Adjure, Sanction) leave the wire and the base path; each becomes an argot pointer below.

## Parameter and field renames

| Tool | Aous | Eurotas | Reason |
|---|---|---|---|
| every tool that took it (20) | instance_id | seat | the value is the seat name |
| message_send | sender (deprecated twin) | dropped | a new contract carries no deprecated twin |
| message_send | coordinates | coordinates (kept) | a stored envelope key on messages and vantages; the content model is not the register, and the wire says the key's name |
| entry_write | horizon, horizon_title | vantage, vantage_title | one concept one term; horizon becomes argot |
| vantage_write | binds | entry | the entry the vantage binds to; vantage_list already filters by `entry` |
| vantage_write | horizon | body | the vantage's text is its body, like every other entry |
| vantage_write, vantage_list, entry_write (responses) | vantage (the kind) | kind | so `vantage` means one thing on the wire; matches the parameter |
| vantage_list (response) | binds, binds_status, horizon | entry, entry_status, body | the same |
| proposal_unstage | — | seat (new) | origin calls name the seat; the caller is recorded |
| seat_whoami (response) | bound_instance | bound_seat | the binding pins a seat |
| seat_whoami (response) | — | tools (new): {count, names} | so a seat can tell a client gap from a build gap (parallax's finding) |
| seat_announce (response) | — | joined (new); note (new, when joined is false) | the join's front door |
| responses | instance, instances | seat, seats | the same |

Verbatim (technical names, MOE100 §4.6): domain, slug, body, title, type, tags, references, supersedes, superseded_by, status, tick, thread, op_id, ref, path, resolve, with_vantages, query, scope, limit, offset, include_superseded, include_weak, kind, author, canon_state, detail, recipients, subject, coordinates, unread_only, message_path, proposal_id, seq, origin_author, reason, code, staged_oid_prefix, term. Entry type codes (kno, log, arg, state, …), domains (state/, messages/, vantages/, meta/log/), and the envelope keys are the content model, not the register: verbatim.

## Argot pointers — the enrichment layer

Every argot term that names a base-path concept keeps its entry (type `arg`) and gains a first line pointing at the base-path term or tool, the way a CNAME points at a canonical name. Argot that names no base-path concept (most of the 76) is untouched. The argot stays reachable through `term_list`; a seat that wants the practice's voice reads it, and an instance that wants to act never needs it.

By the rule's first clause (in the dictionary):

- scry → any read (`*_list`, entry_read, canon_state, seat_state, term_list, server_stats)
- invoke → entry_read · evoke → entry_search · conjure → entry_write · adjure → proposal_append_entry · sanction → the practitioner's land (proposal_land when relayed)
- kip → entry_* — KIP: Knowledge Interface Protocol (ruled 2026-09-05; the "Information" variant is retired)
- imp → message_* — IMP: Instance Message Protocol
- vap → vantage_* — VAP: Vantage Access Protocol
- sup → canon_reconcile, seat_state — SUP: Standing Update Protocol
- map → entry_search — MAP: Manifest Access Protocol
- cap → the server — CAP: Context Access Protocol
- ghost-run → lost response
- legenda → stays a design term of canon (the readable-entire criterion); not on the base path

By the rule's second clause (a plain phrase loses nothing needed for use):

- dock → reference file · river → suite edition · road → the skill body · ship → procedure section · hinge → reconcile · info desk → seat_announce · frontier → live messages · corpse → superseded message · spine, trail → perspective, state entries · fold → entry_write with `vantage` · horizon → vantage · gate → the practitioner

## What this entry does not yet hold

Token counts (T1) wait on a declared tokenizer. Round-trip (T2), swap (T3), and legibility (T5) need runs against a model and a human and are recorded by the build phase; two fresh seats' arrivals (parallax, Skotobolos; 2026-09-06) are the first live T2 evidence and are cited from the recover file, not recorded here as tests. Search (T4) is mechanical and runs when the docks exist. The multi-canon selector, if it rides the same contract, adds a parameter and a term to this glossary by supersession. The unstage authority (relay.md) is attributed at the server but not yet enforced there: the stage call carries no seat, so the server cannot yet know who staged.
