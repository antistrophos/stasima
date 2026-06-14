# SPDX-License-Identifier: Apache-2.0
"""
Multi-instance over shared data: two SEPARATE servers (each its own store/index/audit connections to
the SAME files on disk) — exactly what two Desktop stdio chats produce. Proves IMP flows across them:
a message sent through one server is seen through the other, a reply round-trips, and both instances
are visible. Single-server IMP is covered by server_test; this is the cross-server (real multi-
instance) path, where messages travel through the shared git substrate + map index, not in-process.
"""
import json
import os
import subprocess as sp
import sys
import tempfile

import anyio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stasima.local_capstore import LocalCapStore
from stasima.map_index import SqliteMapIndex, StubEmbedder
from stasima.audit_log import SqliteAuditLog
from stasima.authz import DefaultPolicy
from stasima.cap_server import build_server, compose_entry
from mcp.shared.memory import create_connected_server_and_client_session as connect

work = tempfile.mkdtemp(prefix="cap-multi-")
gd = os.path.join(work, "stasima.git")
sp.run(["git", "init", "--bare", "-q", gd], check=True)
mapdb, auditdb = os.path.join(work, "map.sqlite"), os.path.join(work, "audit.sqlite")
LocalCapStore(gd, approvers={"p"}).bootstrap_canon(
    {"practice/seed.md": compose_entry({"type": "kno", "title": "Seed", "status": "active"}, "seed").encode()},
    "bootstrap")


def make_server():
    # fresh component connections to the same files — a distinct server process's view
    return build_server(LocalCapStore(gd, approvers={"p"}),
                        SqliteMapIndex(mapdb), StubEmbedder(64), SqliteAuditLog(auditdb), DefaultPolicy())


def pay(r):
    sc = getattr(r, "structuredContent", None)
    return sc.get("result", sc) if isinstance(sc, dict) else \
        json.loads("".join(getattr(c, "text", "") for c in r.content))


async def main():
    A, B = make_server(), make_server()               # Sphragis on A, Lintel on B
    async with connect(A) as ca, connect(B) as cb:
        # Sphragis authors to its own perspective, then messages Lintel — all via server A
        await ca.call_tool("imp_send", {"sender": "Sphragis", "recipients": ["Lintel"],
            "subject": "arrived", "body": "first contact", "op_id": "m1",
            "coordinates": ["practice/seed.md"]})

        # Lintel sees it through server B — the message crossed via the shared substrate
        flags = pay(await cb.call_tool("imp_flags", {"instance_id": "Lintel"}))
        inbox = pay(await cb.call_tool("imp_check", {"instance_id": "Lintel"}))["messages"]
        assert flags["unread"] == 1 and inbox[0]["from"] == "Sphragis" \
            and inbox[0]["coordinates"] == ["practice/seed.md"], (flags, inbox)

        # read-state is append-only audit, so it's shared too: mark read on B, clear on B
        await cb.call_tool("imp_mark_read", {"instance_id": "Lintel", "message_path": inbox[0]["path"]})
        assert pay(await cb.call_tool("imp_flags", {"instance_id": "Lintel"}))["unread"] == 0

        # Lintel replies via B; Sphragis sees it via A
        await cb.call_tool("imp_send", {"sender": "Lintel", "recipients": ["Sphragis"],
            "subject": "re: arrived", "body": "welcome", "op_id": "m2"})
        back = pay(await ca.call_tool("imp_check", {"instance_id": "Sphragis"}))["messages"]
        assert back[0]["from"] == "Lintel" and back[0]["subject"] == "re: arrived", back

        # both instances are visible from either server — AND the names survive the wire intact
        # (Lintel's rehearsal bug: a bare list serialized one text block per name, fusing
        # 'Lintel'+'epode' -> 'Lintelepode' on a naive client. The wrapped object can't fuse.)
        for c in (ca, cb):
            res = await c.call_tool("list_instances", {})
            who = pay(res)["instances"]
            assert sorted(who) == ["Lintel", "Sphragis"], who
            joined = "".join(getattr(b, "text", "") for b in res.content)   # what a naive client shows
            assert "Lintelepode" not in joined and "Lintel" in joined and "Sphragis" in joined, joined

        # name-fork guard: 'Sphragis' exists; acting as 'sphragis' (case drift) must be REFUSED at
        # write and WARNED on arrival — a casing drift silently forks identity otherwise (v1: names
        # are case-sensitive; full normalization is 1.1).
        warn = pay(await ca.call_tool("announce", {"instance_id": "sphragis"}))
        assert "name_warning" in warn and "Sphragis" in warn["name_warning"], warn
        forked = await ca.call_tool("kip_commit", {"instance_id": "sphragis", "domain": "practice",
            "slug": "oops", "body": "x", "op_id": "fork-1"})
        assert getattr(forked, "isError", False), "a case-fork write must be refused"
        # the exact name is fine, of course
        ok = await ca.call_tool("kip_commit", {"instance_id": "Sphragis", "domain": "practice",
            "slug": "fine", "body": "x", "op_id": "fork-2"})
        assert not getattr(ok, "isError", False), "the exact existing name must still write"
        print("name-fork guard: 'sphragis' refused + warned, 'Sphragis' writes — OK")

    print("multi-instance OK: IMP send/flag/check/mark-read + reply round-trip across two servers; "
          "both instances visible from each.")


anyio.run(main)
print("OK -- two servers on shared data: messages and read-state travel through the substrate.")
