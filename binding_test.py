# SPDX-License-Identifier: Apache-2.0
"""
Session binding (the SSH-shaped identity pin) acceptance checks:
  1. strict: a matched identity-claiming write proceeds; a mismatched one refuses with the
     ritual in the error text (that seat's own connection / witness mode; no in-call override)
  2. the imp_send identity alias: instance_id= (canonical) and sender= (deprecated twin) both
     work; conflicting twins refused; the original forgery typo now refuses under binding
  3. witness: the mismatched write PROCEEDS and the envelope carries authored_via=<bound> —
     the confession rides git — plus a witness row in the audit log
  4. unbound: open trust unchanged (the regression guard), no stamp, no spawn row
  5. the relay is outside the guard BY SHAPE: stage/land_approve carry no identity param
  6. every bound spawn declares its binding into the audit log (the rekey rotation trail)
  7. whoami surfaces the binding and whether this claim matches
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
from stasima.cap_server import build_server, compose_entry, parse_entry
from mcp.shared.memory import create_connected_server_and_client_session as connect


def setup():
    work = tempfile.mkdtemp(prefix="cap-bind-")
    gd = os.path.join(work, "stasima.git")
    sp.run(["git", "init", "--bare", "-q", gd], check=True)
    store = LocalCapStore(gd, approvers={"practitioner"})
    store.bootstrap_canon({"practice/seed.md": compose_entry(
        {"type": "kno", "title": "Seed", "status": "active"}, "seed").encode()}, "bootstrap")
    return store, SqliteMapIndex(":memory:"), StubEmbedder(dim=64), SqliteAuditLog(":memory:")


def payload(res):
    sc = getattr(res, "structuredContent", None)
    if sc is not None:
        if isinstance(sc, dict) and set(sc.keys()) == {"result"}:
            return sc["result"]
        return sc
    txt = "".join(getattr(c, "text", "") for c in res.content)
    try:
        return json.loads(txt)
    except Exception:
        return txt


def err_text(res):
    return "".join(getattr(c, "text", "") for c in res.content)


async def main():
    # ---- strict (with a dummy airlock so the relay verbs register for the shape check) ----
    store, index, emb, audit = setup()
    mcp = build_server(store, index, emb, audit, None, object(),
                       bound_instance="Verso", binding_mode="strict")
    async with connect(mcp) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}

        ok = payload(await client.call_tool("kip_commit", {"instance_id": "Verso", "domain": "state",
                                                           "slug": "one", "body": "x", "op_id": "b1"}))
        assert ok["author"] == "Verso", ok
        bad = await client.call_tool("kip_commit", {"instance_id": "Recto", "domain": "state",
                                                    "slug": "two", "body": "y", "op_id": "b2"})
        assert getattr(bad, "isError", False), "strict mismatch must refuse"
        assert "bound to 'Verso'" in err_text(bad) and "witness" in err_text(bad), err_text(bad)
        denied = [e for e in audit.events(op="kip_commit") if e["outcome"] == "denied"]
        assert denied and denied[-1]["detail"]["reason"] == "session-binding mismatch", denied
        print("1. strict: matched write OK; mismatch refused with the ritual named")

        a1 = payload(await client.call_tool("imp_send", {"instance_id": "Verso", "recipients": ["Recto"],
                                                         "subject": "s", "body": "b", "op_id": "m1"}))
        assert a1["from"] == "Verso", a1
        a2 = payload(await client.call_tool("imp_send", {"sender": "Verso", "recipients": ["Recto"],
                                                         "subject": "s2", "body": "b2", "op_id": "m2"}))
        assert a2["from"] == "Verso", a2
        both = await client.call_tool("imp_send", {"instance_id": "Verso", "sender": "Recto",
                                                   "recipients": ["Recto"], "subject": "s3",
                                                   "body": "b3", "op_id": "m3"})
        assert getattr(both, "isError", False) and "Exactly one" in err_text(both), err_text(both)
        typo = await client.call_tool("imp_send", {"sender": "Recto", "recipients": ["Verso"],
                                                   "subject": "the original typo shape",
                                                   "body": "b4", "op_id": "m4"})
        assert getattr(typo, "isError", False) and "bound to 'Verso'" in err_text(typo), \
            "the forgery-by-typo class must refuse under a strict binding"
        print("2. imp_send alias: canonical + twin OK, conflict refused, the forgery typo refused")

        stage_props = tools["stage_approve"].inputSchema.get("properties", {})
        land_props = tools["land_approve"].inputSchema.get("properties", {})
        assert "instance_id" not in stage_props and "sender" not in stage_props, stage_props
        assert "instance_id" not in land_props and "sender" not in land_props, land_props
        print("5. relay verbs carry NO identity param — outside the guard by shape")

        w = payload(await client.call_tool("whoami", {"instance_id": "Recto"}))
        assert w["session_binding"] == {"bound_instance": "Verso", "mode": "strict", "match": False}, w
        print("7. whoami surfaces the binding and the match")

    binds = audit.events(op="session_binding")
    assert binds and binds[0]["actor"] == "Verso" and binds[0]["detail"]["mode"] == "strict", binds
    print("6. the spawn's binding declaration is in the audit log (the rekey trail)")

    # ---- witness ----
    store2, index2, emb2, audit2 = setup()
    mcp2 = build_server(store2, index2, emb2, audit2, bound_instance="Verso", binding_mode="witness")
    async with connect(mcp2) as client:
        r = payload(await client.call_tool("kip_commit", {"instance_id": "Recto", "domain": "state",
                                                          "slug": "wit", "body": "witnessed", "op_id": "w1"}))
        assert r["author"] == "Recto", r                     # the write PROCEEDED
        got = payload(await client.call_tool("kip_get", {"ref": "Recto", "path": "state/wit.md"}))
        env, _ = parse_entry(got["text"])
        assert env.get("authored_via") == "Verso", env       # ...and confessed in git
        wit = [e for e in audit2.events(op="kip_commit") if e["outcome"] == "witness"]
        assert wit and wit[0]["detail"]["bound"] == "Verso", wit
        payload(await client.call_tool("imp_send", {"instance_id": "Recto", "recipients": ["Verso"],
                                                    "subject": "w", "body": "wb", "op_id": "wm1"}))
        env2, _ = parse_entry(payload(await client.call_tool(
            "kip_get", {"ref": "Recto", "path": "messages/wm1.md"}))["text"])
        assert env2.get("authored_via") == "Verso", env2
        print("3. witness: mismatched writes proceed; envelope + audit both confess")

    # ---- unbound: the regression guard ----
    store3, index3, emb3, audit3 = setup()
    mcp3 = build_server(store3, index3, emb3, audit3)
    async with connect(mcp3) as client:
        r = payload(await client.call_tool("kip_commit", {"instance_id": "Anyone", "domain": "state",
                                                          "slug": "open", "body": "z", "op_id": "o1"}))
        assert r["author"] == "Anyone", r
        env3, _ = parse_entry(payload(await client.call_tool(
            "kip_get", {"ref": "Anyone", "path": "state/open.md"}))["text"])
        assert "authored_via" not in env3, env3
        assert not audit3.events(op="session_binding")
        print("4. unbound: open trust unchanged — no stamp, no spawn row")

    print("\nOK -- session binding: strict, witness, alias, relay shape, audit trail all pass.")


anyio.run(main)
