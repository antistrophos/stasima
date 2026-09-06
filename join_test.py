# SPDX-License-Identifier: Apache-2.0
"""
The join gate (the practitioner's rule, 2026-09-06): a seat's first write to its perspective is its
::1 state update. Until it is written, every other write is refused with the join call in the
refusal; reads, canon_diff, and canon_reconcile stay open — the new ability first, then the rest.
Proven here:

  1. a fresh seat's entry_write / message_send / vantage_write / proposal_append_entry are refused,
     each refusal naming the join call (errors are instructions);
  2. seat_announce tells the fresh seat: joined=false plus a note carrying the call;
  3. the reconcile is open before the join (canon_diff, canon_reconcile);
  4. a state entry with tick != 1 does not join; tick='1' (or '::1') does, with its vantage folded;
  5. after the join every write opens, and announce says joined=true;
  6. a seat from before the gate (entries, no state update) is never gated;
  7. join_gate=False switches the gate off for a scratch server.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anyio
from mcp.client import Client as connect
from _testkit import fresh_repo, payload, is_err, err_text
from stasima.cap_server import build_server
from stasima.local_capstore import LocalCapStore, Identity, PERSP_PREFIX
from stasima.map_index import SqliteMapIndex, StubEmbedder
from stasima.audit_log import SqliteAuditLog
from stasima.entries import compose_entry

work, gd = fresh_repo("cap-join-")
store = LocalCapStore(gd, approvers={"practitioner"})
index = SqliteMapIndex(os.path.join(work, "map.sqlite"))
audit = SqliteAuditLog(os.path.join(work, "audit.sqlite"))


def server(**kw):
    return build_server(store, index, StubEmbedder(64), audit, binding_mode="off", **kw)
e = lambda t, b: compose_entry({"type": t, "title": "x", "status": "active"}, b).encode()
store.bootstrap_canon({"practice/seed.md": e("kno", "seed"), "meta/log/1.md": e("log", "::1")}, "bootstrap")
canon = store.resolve_ref("refs/heads/main")

# a seat from before the gate: a knowledge entry on its perspective, no state update ever
old_ref = PERSP_PREFIX + "Old"
store.commit(old_ref, {"practice/legacy.md": e("kno", "written before the gate")}, "legacy",
             Identity("Old"), expected_parent=None, op_id="old-1")


async def main():
    async with connect(server()) as c:
        # 1. every write refused, each naming the join call
        for tool, args in [
            ("entry_write", {"domain": "practice", "slug": "first", "body": "b", "op_id": "n1"}),
            ("message_send", {"recipients": ["Old"], "subject": "s", "body": "b", "op_id": "n2"}),
            ("vantage_write", {"entry": "practice/seed.md", "body": "v", "op_id": "n3", "kind": "reconstructed"}),
            ("proposal_append_entry", {"proposal_id": "p-n", "domain": "practice", "slug": "x", "body": "b", "op_id": "n4"}),
        ]:
            r = await c.call_tool(tool, {"seat": "Nova", **args})
            assert is_err(r) and "::1 state update" in err_text(r) and "tick='1'" in err_text(r), (tool, err_text(r))
        print("1. fresh seat: four writes refused, each refusal carries the join call")

        # 2. announce says so
        a = payload(await c.call_tool("seat_announce", {"seat": "Nova"}))
        assert a["joined"] is False and "tick='1'" in a["note"], a
        print("2. seat_announce: joined=false + the note")

        # 3. the reconcile is open before the join
        d = payload(await c.call_tool("canon_diff", {"seat": "Nova"}))
        assert d["first_pull"] is True, d
        rr = payload(await c.call_tool("canon_reconcile", {"seat": "Nova", "body": "first pull; nothing to revise"}))
        assert rr["canon_cursor"] == canon, rr
        # still not joined: a reconcile report is a state entry, not a state update
        r = await c.call_tool("entry_write", {"seat": "Nova", "domain": "practice", "slug": "first", "body": "b", "op_id": "n5"})
        assert is_err(r) and "::1" in err_text(r), err_text(r)
        print("3. reconcile open before the join; the report does not join")

        # 4. tick != 1 does not join; '::1' does, vantage folded
        r = await c.call_tool("entry_write", {"seat": "Nova", "domain": "state", "slug": "seven", "body": "b", "op_id": "n6", "tick": "7"})
        assert is_err(r) and "::1" in err_text(r), err_text(r)
        j = payload(await c.call_tool("entry_write", {"seat": "Nova", "domain": "state", "slug": "arrived", "body": "where I stand",
                                                       "op_id": "n7", "tick": "::1", "vantage": "written against canon ::1"}))
        assert j["path"] == "state/arrived.md" and j["folded"]["kind"] == "confirmed", j
        print("4. tick=7 refused; tick='::1' joins with its vantage folded")

        # 5. everything opens; announce says joined
        w = payload(await c.call_tool("entry_write", {"seat": "Nova", "domain": "practice", "slug": "first", "body": "b", "op_id": "n8"}))
        assert w["path"] == "practice/first.md", w
        m = payload(await c.call_tool("message_send", {"seat": "Nova", "recipients": ["Old"], "subject": "s", "body": "b", "op_id": "n9"}))
        assert m["from"] == "Nova", m
        a2 = payload(await c.call_tool("seat_announce", {"seat": "Nova"}))
        assert a2["joined"] is True and "note" not in a2, a2
        st = payload(await c.call_tool("seat_state", {"seat": "Nova"}))
        assert st["ticks"].get("state/arrived.md") == "1", st["ticks"]
        print("5. after the join: entry, message OK; announce joined=true; seat_state shows ::1")

        # 6. a seat from before the gate is never gated
        w = payload(await c.call_tool("entry_write", {"seat": "Old", "domain": "practice", "slug": "more", "body": "b", "op_id": "o2"}))
        assert w["path"] == "practice/more.md", w
        a3 = payload(await c.call_tool("seat_announce", {"seat": "Old"}))
        assert a3["joined"] is True, a3
        print("6. a seat with entries from before the gate writes freely")

    # 7. the knob
    async with connect(server(join_gate=False)) as c:
        w = payload(await c.call_tool("entry_write", {"seat": "Scratch", "domain": "practice", "slug": "free", "body": "b", "op_id": "s1"}))
        assert w["path"] == "practice/free.md", w
        a = payload(await c.call_tool("seat_announce", {"seat": "Nobody"}))
        assert a["joined"] is False and "note" not in a, a
    print("7. join_gate=False: no gate, no note")


anyio.run(main)
print("\nOK -- the join gate: first write is ::1; reads and the reconcile open; legacy seats untouched; knob works.")
