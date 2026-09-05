# SPDX-License-Identifier: Apache-2.0
"""
Binding at process grain (the SSH-shaped identity pin, with port-security sticky learning):
  1. pinned strict: matched write proceeds; mismatch refuses with the ritual named
  2. the message_send identity alias: instance_id= (canonical) + sender= (deprecated twin); conflict
     refused; the original forgery typo refused under a pinned binding
  3. pinned witness: the mismatched write PROCEEDS and confesses (authored_via in envelope + audit)
  4. STICKY default (no env at all): the first identity-claiming write LEARNS the binding; a second
     identity then refuses (strict default — secure by doing nothing); whoami shows the learning
  5. off = the explicit server-owned rip-cord: no learning, no enforcement, no stamps
  6. PORT durability: a ported definition's learned binding survives a respawn (restored from the
     append-only ledger); a console clear event re-arms learning
  7. the relay verbs carry no identity param (outside the guard BY SHAPE)
  8. every pinned spawn / sticky learn / port restore declares itself into the audit log
"""
import os
import subprocess as sp
import sys
import tempfile

import anyio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stasima.local_capstore import LocalCapStore
from stasima.map_index import SqliteMapIndex, StubEmbedder
from stasima.audit_log import SqliteAuditLog
from stasima.cap_server import build_server, compose_entry, parse_entry, port_bindings
from mcp.client import Client as connect   # v2: the in-process client — one Client, one connection


def setup():
    work = tempfile.mkdtemp(prefix="cap-bind-")
    gd = os.path.join(work, "stasima.git")
    sp.run(["git", "init", "--bare", "-q", gd], check=True)
    store = LocalCapStore(gd, approvers={"practitioner"})
    store.bootstrap_canon({"practice/seed.md": compose_entry(
        {"type": "kno", "title": "Seed", "status": "active"}, "seed").encode()}, "bootstrap")
    return store, SqliteMapIndex(":memory:"), StubEmbedder(dim=64), SqliteAuditLog(":memory:")


from _testkit import payload, err_text   # the suite's shared readers


async def main():
    # ---- pinned strict (dummy airlock so the relay verbs register for the shape check) ----
    store, index, emb, audit = setup()
    mcp = build_server(store, index, emb, audit, None, object(),
                       bound_instance="Verso", binding_mode="strict")
    async with connect(mcp) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}

        ok = payload(await client.call_tool("entry_write", {"instance_id": "Verso", "domain": "state",
                                                           "slug": "one", "body": "x", "op_id": "b1"}))
        assert ok["author"] == "Verso", ok
        bad = await client.call_tool("entry_write", {"instance_id": "Recto", "domain": "state",
                                                    "slug": "two", "body": "y", "op_id": "b2"})
        assert bad.is_error, "strict mismatch must refuse"
        assert "pinned to 'Verso'" in err_text(bad) and "server-owned" in err_text(bad), err_text(bad)
        denied = [e for e in audit.events(op="entry_write") if e["outcome"] == "denied"]
        assert denied and denied[-1]["detail"]["reason"] == "session-binding mismatch", denied
        print("1. pinned strict: matched write OK; mismatch refused with the ritual named")

        a1 = payload(await client.call_tool("message_send", {"instance_id": "Verso", "recipients": ["Recto"],
                                                         "subject": "s", "body": "b", "op_id": "m1"}))
        assert a1["from"] == "Verso", a1
        a2 = payload(await client.call_tool("message_send", {"sender": "Verso", "recipients": ["Recto"],
                                                         "subject": "s2", "body": "b2", "op_id": "m2"}))
        assert a2["from"] == "Verso", a2
        both = await client.call_tool("message_send", {"instance_id": "Verso", "sender": "Recto",
                                                   "recipients": ["Recto"], "subject": "s3",
                                                   "body": "b3", "op_id": "m3"})
        assert both.is_error and "Exactly one" in err_text(both), err_text(both)
        typo = await client.call_tool("message_send", {"sender": "Recto", "recipients": ["Verso"],
                                                   "subject": "the original typo shape",
                                                   "body": "b4", "op_id": "m4"})
        assert typo.is_error and "pinned to 'Verso'" in err_text(typo), \
            "the forgery-by-typo class must refuse under a pinned binding"
        print("2. message_send alias: canonical + twin OK, conflict refused, the forgery typo refused")

        stage_props = tools["proposal_stage"].input_schema.get("properties", {})
        land_props = tools["proposal_land"].input_schema.get("properties", {})
        assert "instance_id" not in stage_props and "sender" not in stage_props, stage_props
        assert "instance_id" not in land_props and "sender" not in land_props, land_props
        print("7. relay verbs carry NO identity param — outside the guard by shape")

        w = payload(await client.call_tool("seat_whoami", {"instance_id": "Recto"}))
        assert w["binding"] == {"mode": "strict", "grain": "process", "bound_instance": "Verso",
                                "source": "pinned", "match": False}, w
        print("8a. whoami surfaces the pinned binding and the match")

    binds = audit.events(op="session_binding")
    assert binds and binds[0]["actor"] == "Verso" and binds[0]["detail"]["source"] == "pinned", binds
    print("8b. the pinned spawn's declaration is in the audit log")

    # ---- pinned witness ----
    store2, index2, emb2, audit2 = setup()
    mcp2 = build_server(store2, index2, emb2, audit2, bound_instance="Verso", binding_mode="witness")
    async with connect(mcp2) as client:
        r = payload(await client.call_tool("entry_write", {"instance_id": "Recto", "domain": "state",
                                                          "slug": "wit", "body": "witnessed", "op_id": "w1"}))
        assert r["author"] == "Recto", r                     # the write PROCEEDED
        env, _ = parse_entry(payload(await client.call_tool(
            "entry_read", {"ref": "Recto", "path": "state/wit.md"}))["text"])
        assert env.get("authored_via") == "Verso", env       # ...and confessed in git
        wit = [e for e in audit2.events(op="entry_write") if e["outcome"] == "witness"]
        assert wit and wit[0]["detail"]["bound"] == "Verso", wit
        print("3. pinned witness: mismatched write proceeds; envelope + audit both confess")

    # ---- sticky default: no env at all -> secure by doing nothing ----
    store4, index4, emb4, audit4 = setup()
    mcp4 = build_server(store4, index4, emb4, audit4)
    async with connect(mcp4) as client:
        w0 = payload(await client.call_tool("seat_whoami", {"instance_id": "Recto"}))
        assert w0["binding"] == {"mode": "strict", "grain": "process", "bound_instance": None,
                                 "source": None, "match": None}, w0
        first = payload(await client.call_tool("entry_write", {"instance_id": "Recto", "domain": "state",
                                                              "slug": "st1", "body": "a", "op_id": "s1"}))
        assert first["author"] == "Recto", first             # first write LEARNS
        learned = [e for e in audit4.events(op="session_binding") if e["detail"].get("learned")]
        assert learned and learned[0]["actor"] == "Recto" and learned[0]["detail"]["source"] == "process"
        w1 = payload(await client.call_tool("seat_whoami", {"instance_id": "Recto"}))
        assert w1["binding"]["bound_instance"] == "Recto" and \
               w1["binding"]["source"] == "process" and w1["binding"]["match"] is True, w1
        again = payload(await client.call_tool("entry_write", {"instance_id": "Recto", "domain": "state",
                                                              "slug": "st2", "body": "b", "op_id": "s2"}))
        assert again["author"] == "Recto", again             # same identity keeps working
        other = await client.call_tool("entry_write", {"instance_id": "Verso", "domain": "state",
                                                      "slug": "st3", "body": "c", "op_id": "s3"})
        assert other.is_error and "learned (sticky) as 'Recto'" in err_text(other), \
            "a second identity through a sticky-learned connection must refuse"
        print("4. sticky default: first write learns, second identity refuses — secure by doing nothing")

    # ---- off: the explicit server-owned rip-cord ----
    store3, index3, emb3, audit3 = setup()
    mcp3 = build_server(store3, index3, emb3, audit3, binding_mode="off")
    async with connect(mcp3) as client:
        r1 = payload(await client.call_tool("entry_write", {"instance_id": "Anyone", "domain": "state",
                                                           "slug": "open", "body": "z", "op_id": "o1"}))
        r2 = payload(await client.call_tool("entry_write", {"instance_id": "Someone", "domain": "state",
                                                           "slug": "open2", "body": "z2", "op_id": "o2"}))
        assert r1["author"] == "Anyone" and r2["author"] == "Someone"
        env3, _ = parse_entry(payload(await client.call_tool(
            "entry_read", {"ref": "Someone", "path": "state/open2.md"}))["text"])
        assert "authored_via" not in env3, env3
        assert not audit3.events(op="session_binding"), "off must not learn"
        w = payload(await client.call_tool("seat_whoami", {"instance_id": "Anyone"}))
        assert w["binding"]["mode"] == "off", w      # the downgrade is visible, like http://
        print("5. off: open trust, no learning, no stamps — and whoami shows the downgrade plainly")

    # ---- port durability: the learned binding survives a respawn; a clear re-arms ----
    store5, index5, emb5, audit5 = setup()
    mcp5a = build_server(store5, index5, emb5, audit5, port_token="port-7")
    async with connect(mcp5a) as client:
        payload(await client.call_tool("entry_write", {"instance_id": "Recto", "domain": "state",
                                                      "slug": "p1", "body": "a", "op_id": "p1"}))
    assert port_bindings(audit5)["port-7"]["instance"] == "Recto"
    mcp5b = build_server(store5, index5, emb5, audit5, port_token="port-7")   # the respawn
    async with connect(mcp5b) as client:
        w = payload(await client.call_tool("seat_whoami", {"instance_id": "Recto"}))
        assert w["binding"] == {"mode": "strict", "grain": "process", "bound_instance": "Recto",
                                "source": "port", "match": True, "port": "port-7"}, w
        other = await client.call_tool("entry_write", {"instance_id": "Verso", "domain": "state",
                                                      "slug": "p2", "body": "b", "op_id": "p2"})
        assert other.is_error, "the restored port binding must enforce with no prior write"
    restored = [e for e in audit5.events(op="session_binding") if e["detail"].get("restored")]
    assert restored and restored[0]["actor"] == "Recto", restored
    audit5.append("practitioner", "port_binding", detail={"port": "port-7", "action": "clear",
                                                          "was": "Recto"})   # the console clear
    assert port_bindings(audit5)["port-7"]["instance"] is None
    mcp5c = build_server(store5, index5, emb5, audit5, port_token="port-7")   # re-armed
    async with connect(mcp5c) as client:
        r = payload(await client.call_tool("entry_write", {"instance_id": "Verso", "domain": "state",
                                                          "slug": "p3", "body": "c", "op_id": "p3"}))
        assert r["author"] == "Verso", "a cleared port must learn its next first-writer"
    assert port_bindings(audit5)["port-7"]["instance"] == "Verso"
    print("6. port sticky: learned -> survives respawn -> console clear re-arms -> relearns")

    print("\nOK -- binding (process grain): pinned, sticky, port-durable, off, alias, relay shape all pass.")


anyio.run(main)
