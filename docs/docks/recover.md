# The recover dock

The routine library for the two kinds of failure: **refusals** (a guard threw — the error text is the spec for the corrected act) and **process drift** (nothing threw — you catch yourself). Each routine: name → symptom → press-this fix-sequence → which calls. Evidence-honest throughout: routines the practice actually hit are CONFIRMED; rules nobody hit are marked *(anticipated)* — completeness-theater refused.

- **Tools wielded (recover-only clusters):** [`propose`](../tools.md#propose) + [`conflict_preview`](../tools.md#conflict_preview) (the Adjure retry) · [`kip_get`](../tools.md#kip_get) with `resolve="exact"` + [`list_entries`](../tools.md#list_entries) (the deliberate-read navigation) — everything else reuses the other docks' calls.
- **Skill encoding:** [`skills/atrax/atrax-recover/SKILL.md`](../../skills/atrax/atrax-recover/SKILL.md)
- **Canon source:** `technical/suites/atrax/recover-v2.md` (the ::E edition — live-resolution made the corpse-read deliberate; adds the fold's op_id-reuse guard and read-the-frontier-first).
- **Design record:** every CONFIRMED routine cites the recorded incident it was distilled from — the library is the practice's own scar tissue, pressed into buttons.
