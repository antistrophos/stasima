# The relay dock

The practitioner approves a landing *through* an instance — TOTP codes spoken in conversation. The highest-consequence, lowest-frequency dock; its failure mode is exploitation, not confusion. Four hard invariants, each carried with its why: **relay, not sanction** · **never solicit codes** · **declining is free** · **codes are the practitioner's only** (you authenticate the channel, not the number). The two-code airlock never collapses into one code.

- **Tools wielded:** [`stage_approve`](../tools.md#stage_approve) · [`land_approve`](../tools.md#land_approve) · [`stage_revert`](../tools.md#stage_revert) (free, never takes a code)
- **Skill encoding:** [`skills/aliakmon/aliakmon-relay/SKILL.md`](../../skills/aliakmon/aliakmon-relay/SKILL.md)
- **Canon source:** `technical/suites/aliakmon/relay.md`.
- **Design record:** adversarially cold-tested before first use; the airlock's mechanics (floor > worst-case code lifetime, content-binding to the staged oid) are in [ARCHITECTURE.md](../../ARCHITECTURE.md) and `stasima/airlock.py`'s own comments.
