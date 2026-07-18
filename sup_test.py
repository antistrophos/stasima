# SPDX-License-Identifier: Apache-2.0
"""
Proves SUP + canon coherence through the MCP client:
  - body-immutability guard on kip_commit (supersede, don't overwrite)
  - the reconcile-before-propose chain: propose blocked -> canon_diff (loads the diff) -> sup_reconcile
    (forced self-report, gated on having pulled) -> propose allowed
  - a canon land re-staleness: propose blocked again -> re-pull -> re-reconcile -> propose allowed
  - three-way agreement (audit canon_pull + reconcile_report, git state/ entry) on the same canon oid
  - sup_state / sup_who / canon_state symmetry
"""
import json
import os
import subprocess as sp
import sys
import tempfile

import anyio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stasima.local_capstore import LocalCapStore, Identity, Approval
from stasima.map_index import SqliteMapIndex, StubEmbedder, index_entry
from stasima.audit_log import SqliteAuditLog
from stasima.authz import DefaultPolicy
from stasima.cap_server import build_server, compose_entry, land_and_record
from stasima.canon import reindex_from_git
from stasima.entries import parse_entry
from mcp.shared.memory import create_connected_server_and_client_session as connect

CANON = "refs/heads/main"
def persp(i): return f"refs/cap/perspectives/{i}"


def payload(res):
    sc = getattr(res, "structuredContent", None)
    if sc is not None:
        return sc["result"] if isinstance(sc, dict) and set(sc.keys()) == {"result"} else sc
    txt = "".join(getattr(c, "text", "") for c in res.content)
    try:
        return json.loads(txt)
    except Exception:
        return txt


def err(res):
    return bool(getattr(res, "isError", False))


def setup():
    work = tempfile.mkdtemp(prefix="cap-sup-")
    gd = os.path.join(work, "stasima.git")
    sp.run(["git", "init", "--bare", "-q", gd], check=True)
    store = LocalCapStore(gd, approvers={"practitioner"})
    index, emb, audit = SqliteMapIndex(":memory:"), StubEmbedder(dim=64), SqliteAuditLog(":memory:")
    env = {"type": "kno", "title": "Seed", "status": "active"}
    store.bootstrap_canon({"practice/seed.md": compose_entry(env, "the seed").encode()}, "bootstrap")
    # index as bootstrap does (reindex derives canon positions): the seed sits at spine position 1
    index_entry(index, emb, ref=CANON, path="practice/seed.md", is_canon=True, authoring_instance="practitioner",
                content_oid=store.resolve_ref(CANON), envelope={**env, "instance_depth": 1}, body="the seed")
    return store, index, emb, audit


async def main():
    store, index, emb, audit = setup()
    # many seats speak through this one connection — the server-owned bypass; binding_test owns the guard
    mcp = build_server(store, index, emb, audit, DefaultPolicy(), binding_mode="off")
    async with connect(mcp) as client:
        async def call(name, **kw):
            return await client.call_tool(name, kw)

        # --- body immutability ---
        assert not err(await call("kip_commit", instance_id="r2", domain="practice", slug="notes", body="Body A", op_id="k1"))
        assert err(await call("kip_commit", instance_id="r2", domain="practice", slug="notes", body="Body B", op_id="k2")), \
            "overwriting an existing body must be denied"
        assert not err(await call("kip_commit", instance_id="r2", domain="practice", slug="notes2", body="Body C", op_id="k3")), \
            "a new slug is fine"
        # a fresh perspective is BORN at depth 1 — no canon fallback on a parentless first commit
        first = store.read_blob(persp("r2"), "practice/notes.md").decode()
        assert "instance_depth: 1" in first, "fresh perspective's first commit must pin depth 1"
        print("body-immutability   OK")

        # --- reconcile-before-propose ---
        assert err(await call("propose", instance_id="r2", proposal_id="p-1", domain="practice",
                              slug="principle", body="a principle", op_id="pr1")), "propose blocked before reconcile"
        # sup_reconcile without pulling is also blocked
        assert err(await call("sup_reconcile", instance_id="r2", body="skipping the read")), "reconcile needs a pull first"

        cd = payload(await call("canon_diff", instance_id="r2"))
        assert any(c["path"] == "practice/seed.md" for c in cd["changed"]), "first pull loads all canon"
        # pointer diff: full bodies must NOT ride along (a large land would overflow the response and
        # break the reconcile hinge for every non-author seat) — titles/status do, so the map is triageable
        assert all("content" not in c for c in cd["changed"]), "diff returns pointers, never full bodies"
        assert all("title" in c for c in cd["changed"] if not c.get("removed")), "pointers carry the envelope"
        assert cd["changed_count"] == len(cd["changed"])
        sr = payload(await call("sup_reconcile", instance_id="r2", body="I've read current canon."))
        old_tip = sr["canon_cursor"]
        # dedup names its referent: a replayed reconcile must say WHAT it duplicated (path+oid+subject),
        # so a ghost-run hunt costs zero extra reads (the soak's ghost-run finding)
        dup = payload(await call("sup_reconcile", instance_id="r2", body="same cursor again"))
        assert dup["already"] is True and dup["oid"] == sr["oid"], "dedup carries the prior commit's oid"
        assert dup.get("subject"), "dedup carries the prior commit's subject"
        # kip_history speaks the pointer grammar: each version carries its title (and .md normalizes)
        kh = payload(await call("kip_history", ref="r2", path="practice/notes"))
        assert kh["history"] and kh["history"][0]["title"] == "notes", "history versions carry titles"
        # tick= (the mirror field, conventions v3): state-scope + hex-form are structure; the value
        # is the seat's — accepted, normalized, surfaced; never compared to prose or history
        assert err(await call("kip_commit", instance_id="r2", domain="practice", slug="no-tick-here",
                              body="x", op_id="t1", tick="2")), "tick off state/ must be refused"
        assert err(await call("kip_commit", instance_id="r2", domain="state", slug="bad-tick",
                              body="x", op_id="t2", tick="xyz")), "non-hex tick must be refused"
        tk = payload(await call("kip_commit", instance_id="r2", domain="state", slug="r2-tick-1a",
                                body="Tick ::1a declared, field mirrored.", op_id="t3", tick="::1A"))
        assert not err(await call("sup_state", instance_id="r2")) and tk["oid"]
        ss = payload(await call("sup_state", instance_id="r2"))
        assert ss["ticks"].get("state/r2-tick-1a.md") == "1a", ss["ticks"]  # normalized: lowercase, no '::'
        mpt = payload(await call("my_perspective", instance_id="r2"))
        row = next(e for e in mpt["entries"] if e["path"] == "state/r2-tick-1a.md")
        assert row.get("tick") == "1a", "listing pointer carries the declared tick"
        assert all("tick" not in e for e in mpt["entries"] if e["path"] != "state/r2-tick-1a.md"), \
            "absence is normal: un-ticked pointers carry NO tick key"
        assert not err(await call("propose", instance_id="r2", proposal_id="p-1", domain="practice",
                                  slug="principle", body="a principle", op_id="pr1")), "propose allowed after reconcile"
        # every proposal carries its log entry (canon sits at ::3B pre-land, so this one is ::3C)
        assert not err(await call("propose", instance_id="r2", proposal_id="p-1", domain="meta/log",
                                  slug="3c", body="::3C — first land in the new substrate.",
                                  op_id="pr1-log", type="log", seq="3c"))
        print("reconcile->propose  OK")

        # --- a canon land re-staleness (practitioner lands p-1 out of band) ---
        prepared = store.prepare_merge("refs/cap/proposals/p-1")
        land_and_record(store, index, emb, audit, prepared, Approval(prepared.candidate_oid, "practitioner", "cli"))
        new_tip = store.resolve_ref(CANON)
        assert new_tip != old_tip

        # D-prime (the pin-leak fix): canon ROWS carry canon's OWN clock — the first-parent spine
        # position of the introducing commit — while the landed entry's ENVELOPE keeps its authoring
        # coordinates (proposal-branch depth), true and resolvable through the merge ancestry forever.
        def row_depth(path):
            r = index.conn.execute("SELECT instance_depth FROM map_entries WHERE ref=? AND path=?",
                                   (CANON, path)).fetchone()
            return r["instance_depth"] if r else None
        assert row_depth("practice/seed.md") == 1, "bootstrap entry sits at canon position 1"
        assert row_depth("practice/principle.md") == 2, "landed entry sits at canon position 2 (the merge)"
        assert row_depth("meta/log/3c.md") == 2, "the land's log entry shares the land's position"
        log_env = parse_entry(store.read_blob(CANON, "meta/log/3c.md").decode())[0]
        assert int(log_env["instance_depth"]) == 3, \
            "the envelope keeps the AUTHORING coordinate (3rd commit on the proposal branch)"
        assert int(log_env["instance_depth"]) != row_depth("meta/log/3c.md"), \
            "two coordinate systems, never conflated in one column"
        # the derivation is deterministic: a fresh reindex reproduces the same canon positions
        reindex_from_git(store, index, emb)
        assert row_depth("practice/principle.md") == 2 and row_depth("practice/seed.md") == 1
        print("canon positions      OK (derived, envelope untouched)")

        assert err(await call("propose", instance_id="r2", proposal_id="p-2", domain="practice",
                              slug="principle2", body="another", op_id="pr2")), "stale again after a land"
        cd2 = payload(await call("canon_diff", instance_id="r2"))
        assert any(c["path"] == "practice/principle.md" for c in cd2["changed"]), "pull loads the landed change"
        # the land's log narrative rides in FULL (small by design; the story exists for the reconciling seat)
        assert any(l["path"] == "meta/log/3c.md" and "::3C" in l["body"] for l in cd2["logs"]), \
            "the log narrative rides the diff in full"
        assert all("content" not in c for c in cd2["changed"]), "incremental diff is pointers too"
        # lifecycle across a real land: the landed proposal reads landed (off-spine ancestry), and a
        # branch opened at the OLD canon reads open with the mechanical lands_behind surfaced
        store.create_branch("refs/cap/proposals/p-behind", old_tip)
        lp = payload(await call("list_proposals"))
        assert lp["statuses"]["p-1"]["status"] == "landed", lp["statuses"]["p-1"]
        assert lp["statuses"]["p-behind"] == {"status": "open", "lands_behind": 1}, lp["statuses"]["p-behind"]
        payload(await call("sup_reconcile", instance_id="r2", body="Read the new principle; adjusting."))
        assert not err(await call("propose", instance_id="r2", proposal_id="p-2", domain="practice",
                                  slug="principle2", body="another", op_id="pr2")), "propose allowed after re-reconcile"
        print("land->re-reconcile  OK")

        # --- three-way agreement on new_tip ---
        recon = store.read_blob(persp("r2"), f"state/reconciled-{new_tip[:12]}.md").decode()
        assert f"canon_cursor: {new_tip}" in recon, "git entry carries the canon cursor"
        evs = audit.events(actor="r2")
        assert any(e["op"] == "canon_pull" and e["result_oid"] == new_tip for e in evs), "audit pull at new_tip"
        assert any(e["op"] == "reconcile_report" and e["detail"].get("canon_cursor") == new_tip for e in evs), "audit report at new_tip"
        print("three-way agreement OK")

        # --- symmetry reads ---
        ss = payload(await call("sup_state", instance_id="r2"))
        assert ss["current_with_canon"] and any("reconciled-" in p for p in ss["state_entries"])
        sw = payload(await call("sup_who"))["instances"]
        assert {"instance": "r2", "current_with_canon": True} in sw
        cs = payload(await call("canon_state"))
        assert cs["canon_tip"] == new_tip and len(cs["lands"]) >= 1
        print("sup_state/who/canon OK")

        ok, bad = audit.verify()
        assert ok, (ok, bad)
        print("\nOK -- SUP coherence: immutability, reconcile-gate, re-staleness, three-way agreement, symmetry.")


anyio.run(main)
