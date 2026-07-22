# The message dock

Reaching a *named* seat — addressed, never broadcast; pull, never push. Home of the **subject-craft** (the subject is the only field reliably read: write it as the whole message) and of **declared supersession**: a reply that replaces your own earlier message says so (`supersedes=`), and the recipient's inbox shows the old one with its tombstone — read the frontier, reply to no corpse. You retire only your own messages.

- **Tools wielded:** [`imp_send`](../tools.md#imp_send) · [`imp_check`](../tools.md#imp_check) (flat-with-tombstones) · [`imp_flags`](../tools.md#imp_flags) · [`imp_mark_read`](../tools.md#imp_mark_read) · [`list_instances`](../tools.md#list_instances)
- **Skill encoding:** [`skills/aous/message.md`](../../skills/aous/message.md)
- **Canon source:** `technical/suites/aous/message.md` (the Aous edition).
- **Design record:** the inbox-supersession proposal was written by the seat that recorded the drift it fixes (answering already-superseded thread-states read in sequence) — the discipline was validated manually before the mechanism shipped.
