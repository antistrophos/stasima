# SPDX-License-Identifier: Apache-2.0
"""
Full-loop test through the real MCP client/protocol path (in-memory transport):
orient -> author (indexed inline) -> map_search -> read own trail -> propose -> check status
-> message peers -> flag/inbox/read. Uses the deterministic StubEmbedder (offline).
"""
import json
import os
import subprocess as sp
import sys
import tempfile

import anyio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stasima.local_capstore import LocalCapStore
from stasima.map_index import SqliteMapIndex, StubEmbedder, index_entry
from stasima.audit_log import SqliteAuditLog
from stasima.authz import DefaultPolicy
from stasima.cap_server import build_server, compose_entry, parse_entry, reindex_from_git
from mcp.shared.memory import create_connected_server_and_client_session as connect


def setup():
    work = tempfile.mkdtemp(prefix="cap-full-")
    gd = os.path.join(work, "stasima.git")
    sp.run(["git", "init", "--bare", "-q", gd], check=True)
    store = LocalCapStore(gd, approvers={"practitioner"})
    index, emb, audit = SqliteMapIndex(":memory:"), StubEmbedder(dim=64), SqliteAuditLog(":memory:")
    # bootstrap a canon entry and index it (simulating the initial/promotion index pass)
    env = {"type": "kno", "title": "No silent loss", "status": "active", "tags": ["durability"]}
    body = "Durability: the git substrate must never silently lose committed work or history."
    store.bootstrap_canon({"practice/no-silent-loss.md": compose_entry(env, body).encode()}, "Bootstrap canon")
    index_entry(index, emb, ref="refs/heads/main", path="practice/no-silent-loss.md", is_canon=True,
                authoring_instance="practitioner", content_oid=store.resolve_ref("refs/heads/main"),
                envelope=env, body=body)
    return store, index, emb, audit


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


async def main():
    store, index, emb, audit = setup()
    mcp = build_server(store, index, emb, audit, DefaultPolicy())
    async with connect(mcp) as client:   # default: tool errors come back as CallToolResult(isError=True)
        names = sorted(t.name for t in (await client.list_tools()).tools)
        print(f"{len(names)} tools:", ", ".join(names))

        await client.call_tool("announce", {"instance_id": "research-2"})

        # author into perspectives (indexed inline)
        await client.call_tool("kip_commit", {"instance_id": "research-2", "domain": "practice",
            "slug": "durability-notes", "body": "Notes on durability and never losing committed work; append-only git history.",
            "op_id": "op-1", "title": "Durability notes", "references": ["practice/no-silent-loss.md"]})
        await client.call_tool("kip_commit", {"instance_id": "research-7", "domain": "practice",
            "slug": "scaling-notes", "body": "Scaling throughput and performance under concurrent request load.",
            "op_id": "op-2", "title": "Scaling notes"})

        # search — attributed, scoped
        allhits = payload(await client.call_tool("map_search", {"instance_id": "research-2",
            "query": "how do we avoid losing committed work durability", "scope": "all"}))["results"]
        print("map_search all:")
        for h in allhits:
            print(f"   {h['score']:>6}  {h['author']:12} canon={h['is_canon']!s:5} {h['path']}")
        canon_only = payload(await client.call_tool("map_search", {"instance_id": "research-2",
            "query": "durability", "scope": "canon"}))["results"]
        mine7 = payload(await client.call_tool("map_search", {"instance_id": "research-7",
            "query": "durability", "scope": "mine"}))["results"]
        print("map_search canon:", [h["path"] for h in canon_only])
        print("map_search mine(r-7):", [h["path"] for h in mine7])

        mp = payload(await client.call_tool("my_perspective", {"instance_id": "research-2"}))
        got = payload(await client.call_tool("kip_get", {"ref": "research-2", "path": "practice/durability-notes.md"}))
        # listings are triageable pointers, not bare paths — title/status/type ride along from the index
        assert all("path" in e and "status" in e and "title" in e for e in mp["entries"]), \
            "my_perspective entries are enriched pointers"
        le = payload(await client.call_tool("list_entries", {"ref": "canon"}))
        assert all("path" in e and "status" in e for e in le["entries"]), "list_entries entries are enriched pointers"
        # a PATH-FILTERED listing must return FULL paths with enrichment intact — subtree-relative
        # names miss every index key (blank fields) and are unusable as coordinates (Shannon's finding)
        lf = payload(await client.call_tool("list_entries", {"ref": "canon", "path": "practice/"}))
        assert lf["entries"], "filtered listing returns the subtree"
        assert all(e["path"].startswith("practice/") for e in lf["entries"]), "filtered listing keeps full paths"
        assert any(e["title"] for e in lf["entries"]), "filtered listing keeps enrichment"
        print("my_perspective:", [e["path"] for e in mp["entries"]])

        # reconcile with canon before proposing (the coherence gate now requires it)
        await client.call_tool("canon_diff", {"instance_id": "research-2"})
        await client.call_tool("sup_reconcile", {"instance_id": "research-2", "body": "Read current canon."})

        # propose + track
        await client.call_tool("propose", {"instance_id": "research-2", "proposal_id": "p-1",
            "domain": "practice", "slug": "principle-durability", "body": "Promote durability to a stated principle.",
            "op_id": "op-3", "title": "Durability principle"})
        cp = payload(await client.call_tool("conflict_preview", {"proposal_id": "p-1"}))
        ps = payload(await client.call_tool("proposal_status", {"proposal_id": "p-1"}))
        print("conflict_preview:", cp, "| proposal_status:", ps["status"])

        # retraction: creator-only lane (audited denial), and every retract writes operation-truth
        r9 = await client.call_tool("propose_retract", {"instance_id": "research-9", "proposal_id": "p-1",
                                                        "path": "practice/principle-durability.md", "op_id": "rx-1"})
        assert getattr(r9, "isError", False), "cross-instance retract must be denied"
        denial = [e for e in audit.events(op="propose_retract") if e["outcome"] == "denied"]
        assert denial and denial[-1]["actor"] == "research-9" and denial[-1]["detail"]["owner"] == "research-2"
        ok_r = await client.call_tool("propose_retract", {"instance_id": "research-2", "proposal_id": "p-1",
                                                          "path": "practice/principle-durability.md", "op_id": "rx-2"})
        assert not getattr(ok_r, "isError", False), "creator's own retract must succeed"
        evs = [e for e in audit.events(op="propose_retract") if e["outcome"] == "ok"]
        assert evs and evs[-1]["actor"] == "research-2" and evs[-1]["target_path"] == "practice/principle-durability.md"             and evs[-1]["result_oid"], "retraction must write full operation-truth"
        assert "practice/principle-durability.md" not in store.list_paths("refs/cap/proposals/p-1"),             "retracted path must actually leave the proposal tree"
        print("retract lane: cross-instance denied (audited) | own retract OK (audited, content gone)")
        # retract of a CANON-HELD path reverts to canon's edition (zero divergence) — never deletes,
        # so a retract can't construct a canon-deletion for the land guard to refuse (Lintel's finding)
        seed = store.read_blob("refs/heads/main", "practice/no-silent-loss.md").decode()
        await client.call_tool("propose", {"instance_id": "research-2", "proposal_id": "p-1",
            "domain": "practice", "slug": "no-silent-loss", "body": seed.split("---")[-1].strip(),
            "op_id": "op-3flip", "title": "No silent loss", "status": "superseded"})
        await client.call_tool("propose_retract", {"instance_id": "research-2", "proposal_id": "p-1",
                                                   "path": "practice/no-silent-loss.md", "op_id": "rx-3"})
        assert "practice/no-silent-loss.md" in store.list_paths("refs/cap/proposals/p-1"), \
            "canon-held path must SURVIVE its retract (reverted, not deleted)"
        cp2 = payload(await client.call_tool("conflict_preview", {"proposal_id": "p-1"}))
        assert "practice/no-silent-loss.md" not in cp2["removes"], "retract must not read as a canon-deletion"
        assert "practice/no-silent-loss.md" not in cp2["modifies"], "reverted path must show zero divergence"
        # log entries fail fast at propose-time: missing/malformed seq refuses HERE, not at the land
        bad_log = await client.call_tool("propose", {"instance_id": "research-2", "proposal_id": "p-1",
            "domain": "meta/log", "slug": "3c", "body": "no seq given", "op_id": "op-badlog", "type": "log"})
        assert getattr(bad_log, "isError", False), "meta/log without seq must refuse at propose-time"
        mism = await client.call_tool("propose", {"instance_id": "research-2", "proposal_id": "p-1",
            "domain": "meta/log", "slug": "3c", "body": "x", "op_id": "op-mismlog", "type": "log", "seq": "3d"})
        assert getattr(mism, "isError", False), "log slug != seq must refuse at propose-time"
        print("retract reverts canon-held paths | meta/log fails fast at propose OK")
        # THE CROSS-PROPOSE ATTRIBUTION GUARD: carrying another seat's work toward canon requires
        # origin_author — silent reattribution refused on BOTH axes (path under another name; verbatim
        # body anywhere), the declared origin must match the evidence, and the gate sees both names
        await client.call_tool("kip_commit", {"instance_id": "research-2", "domain": "practice",
            "slug": "attribution-src", "body": "Attribution is provenance made durable.", "op_id": "as-1"})
        await client.call_tool("canon_diff", {"instance_id": "research-9"})
        await client.call_tool("sup_reconcile", {"instance_id": "research-9", "body": "Read current canon."})
        sil = await client.call_tool("propose", {"instance_id": "research-9", "proposal_id": "p-x",
            "domain": "practice", "slug": "attribution-src", "body": "Attribution is provenance made durable.",
            "op_id": "px-1"})
        assert getattr(sil, "isError", False) and "research-2" in str(sil.content), \
            "silent cross-propose (path+body match) must refuse, naming the origin"
        ren = await client.call_tool("propose", {"instance_id": "research-9", "proposal_id": "p-x",
            "domain": "practice", "slug": "renamed-carriage", "body": "Attribution is provenance made durable.",
            "op_id": "px-2"})
        assert getattr(ren, "isError", False), "verbatim body under a NEW slug must still refuse (rename-bypass closed)"
        lie = await client.call_tool("propose", {"instance_id": "research-9", "proposal_id": "p-x",
            "domain": "practice", "slug": "renamed-carriage", "body": "Attribution is provenance made durable.",
            "op_id": "px-3", "origin_author": "research-7"})
        assert getattr(lie, "isError", False), "an origin_author contradicting the matched evidence must refuse"
        ok_x = await client.call_tool("propose", {"instance_id": "research-9", "proposal_id": "p-x",
            "domain": "practice", "slug": "renamed-carriage", "body": "Attribution is provenance made durable.",
            "op_id": "px-4", "origin_author": "research-2"})
        assert not getattr(ok_x, "isError", False), "carriage WITH true origin must pass"
        carried = store.read_blob("refs/cap/proposals/p-x", "practice/renamed-carriage.md").decode()
        assert "origin_author: research-2" in carried, "the envelope carries the true author"
        cpx = payload(await client.call_tool("conflict_preview", {"proposal_id": "p-x"}))
        att = cpx["attributions"].get("practice/renamed-carriage.md")
        assert att and att["authored"] == "research-2" and att["proposed"] == "research-9", cpx["attributions"]
        print("cross-propose guard: silence refused (both axes) | lie refused | labeled carriage passes, gate sees both names OK")
        # THE RESERVED thread= TAG: ref-safe form guarded on all three carriers (commit/propose/send);
        # value semantics unruled; declared tags scry without the hinge (registry + per-tag pointers)
        for bad in ("Has Space", "UPPER", "-leads", "x" * 65):
            b = await client.call_tool("kip_commit", {"instance_id": "research-2", "domain": "practice",
                "slug": f"bad-{len(bad)}", "body": "x", "op_id": f"th-bad-{len(bad)}", "thread": bad})
            assert getattr(b, "isError", False), f"non-ref-safe tag {bad!r} must refuse"
        await client.call_tool("kip_commit", {"instance_id": "research-2", "domain": "practice",
            "slug": "thread-entry", "body": "A threaded entry.", "op_id": "th-1", "thread": "weave-test"})
        assert not getattr(await client.call_tool("propose", {"instance_id": "research-9",
            "proposal_id": "p-x", "domain": "practice", "slug": "threaded-prop",
            "body": "A threaded proposal entry.", "op_id": "th-2", "thread": "weave-test"}), "isError", False)
        assert not getattr(await client.call_tool("imp_send", {"sender": "research-2",
            "recipients": ["research-9"], "subject": "threaded note", "body": "chained",
            "op_id": "th-msg-1", "thread": "weave-test"}), "isError", False)
        reg = payload(await client.call_tool("thread_scry", {}))
        assert "weave-test" in reg["threads"] and reg["threads"]["weave-test"]["count"] >= 2, reg["threads"]
        one = payload(await client.call_tool("thread_scry", {"thread": "weave-test"}))
        got_types = {e["type"] for e in one["entries"]}
        assert {"kno", "msg"} <= got_types and one["total"] >= 2, one
        print("thread= reserved: form guarded x3 carriers | scry registry + per-tag pointers OK")
        # restore the entry so nothing downstream changes
        await client.call_tool("propose", {"instance_id": "research-2", "proposal_id": "p-1", "domain": "practice",
                                           "slug": "principle-durability", "body": "Promote durability to a stated principle.",
                                           "op_id": "op-3b", "title": "Durability principle"})

        # supersede-not-edit: the lineage the skill teaches must actually be authorable + readable
        # (research-2 authored practice/durability-notes.md earlier; supersede it with a v2)
        await client.call_tool("kip_commit", {"instance_id": "research-2", "domain": "practice",
            "slug": "durability-v2", "body": "Durability, restated with the airlock in mind.", "op_id": "sup-1",
            "title": "Durability v2", "references": ["practice/no-silent-loss.md"],
            "supersedes": ["practice/durability-notes.md"]})
        env2, _ = parse_entry(payload(await client.call_tool("kip_get",
            {"ref": "research-2", "path": "practice/durability-v2.md"}))["text"])
        assert env2.get("supersedes") == ["practice/durability-notes.md"] \
            and env2.get("references") == ["practice/no-silent-loss.md"], env2
        # retire the old entry: metadata-only re-commit (same body) flips status — immutability still holds
        old_body = parse_entry(store.read_blob("refs/cap/perspectives/research-2", "practice/durability-notes.md").decode())[1]
        await client.call_tool("kip_commit", {"instance_id": "research-2", "domain": "practice", "slug": "durability-notes",
            "body": old_body, "op_id": "sup-2", "title": "Durability notes", "status": "superseded",
            "superseded_by": ["practice/durability-v2.md"]})
        env1, _ = parse_entry(store.read_blob("refs/cap/perspectives/research-2", "practice/durability-notes.md").decode())
        assert env1["status"] == "superseded" and env1["superseded_by"] == ["practice/durability-v2.md"], env1
        # live-resolution: a base-path fetch now follows the tombstone to the LIVING edition, chain visible
        live = payload(await client.call_tool("kip_get", {"ref": "research-2", "path": "practice/durability-notes.md"}))
        assert live["path"] == "practice/durability-v2.md" and live["resolved_from"] == ["practice/durability-notes.md"], live
        # resolve='exact' still reads the retired edition deliberately; a missing '.md' is normalized on the way in
        corpse = payload(await client.call_tool("kip_get",
            {"ref": "research-2", "path": "practice/durability-notes", "resolve": "exact"}))
        assert corpse["path"] == "practice/durability-notes.md" and corpse["status"] == "superseded", corpse
        # a miss on the asked ref NAMES where the path actually lives — the error is the instruction
        miss = await client.call_tool("kip_get", {"ref": "research-7", "path": "practice/durability-v2.md"})
        assert getattr(miss, "isError", False) and "research-2" in str(miss.content), miss.content
        # FEATURE A — live-only search by default; include_superseded is the deliberate opt-in,
        # and the hit carries its status so the retired edition is apparent
        live_hits = payload(await client.call_tool("map_search",
            {"instance_id": "research-2", "query": "durability", "scope": "mine"}))["results"]
        assert not any(h["path"] == "practice/durability-notes.md" for h in live_hits), live_hits
        all_hits = payload(await client.call_tool("map_search",
            {"instance_id": "research-2", "query": "durability", "scope": "mine",
             "include_superseded": True}))["results"]
        dead = [h for h in all_hits if h["path"] == "practice/durability-notes.md"]
        assert dead and dead[0]["status"] == "superseded", all_hits
        # and a different body on the same path is still refused (the guard the flip rode through)
        bad = await client.call_tool("kip_commit", {"instance_id": "research-2", "domain": "practice",
            "slug": "durability-notes", "body": "secretly rewritten", "op_id": "sup-3"})
        assert getattr(bad, "isError", False), "body change must still be refused"
        # relevance floor: below-floor hits are withheld WITH a count (an empty result says "N weak
        # matches withheld", never just silence); include_weak returns them; the stub's own default
        # floor is 0 = off (live calibration showed its scores cannot separate true hits from junk)
        assert type(emb).score_floor == 0.0, "stub ships with the floor OFF"
        emb.score_floor = 0.99   # force: every stub score sits below this
        floored = payload(await client.call_tool("map_search",
            {"instance_id": "research-2", "query": "durability", "scope": "mine"}))
        assert floored["results"] == [] and floored["below_floor"] > 0, floored
        weak = payload(await client.call_tool("map_search",
            {"instance_id": "research-2", "query": "durability", "scope": "mine", "include_weak": True}))
        assert weak["results"] and weak["below_floor"] == 0, weak
        emb.score_floor = 0.0    # restore — later searches in this test must see hits again
        print("relevance floor: withheld-with-count + include_weak opt-in OK")
        print("supersede: forward link + metadata-flip authorable, body still immutable OK")

        # message multiple recipients, flag, inbox, read
        await client.call_tool("imp_send", {"sender": "research-2", "recipients": ["research-7", "recto"],
            "subject": "Durability is load-bearing", "body": "Look before proposing scaling changes.",
            "op_id": "m-1", "coordinates": ["practice/no-silent-loss.md"]})
        flag7 = payload(await client.call_tool("imp_flags", {"instance_id": "research-7"}))
        inbox7 = payload(await client.call_tool("imp_check", {"instance_id": "research-7"}))["messages"]
        print("imp_flags r-7:", flag7, "| inbox r-7:", [(m["from"], m["subject"], m["coordinates"]) for m in inbox7])
        await client.call_tool("imp_mark_read", {"instance_id": "research-7", "message_path": "messages/m-1.md"})
        after = payload(await client.call_tool("imp_flags", {"instance_id": "research-7"}))
        recto = payload(await client.call_tool("imp_check", {"instance_id": "recto"}))["messages"]
        print("imp_flags r-7 after read:", after, "| inbox recto:", [m["path"] for m in recto])

        # FEATURE C — inbox supersession, flat-with-tombstones: a reply that supersedes an earlier
        # message tombstones it AT NAVIGATION; nothing is hidden (visibility, not refusal)
        await client.call_tool("imp_send", {"sender": "research-2", "recipients": ["research-7"],
            "subject": "Durability restated — supersedes m-1", "body": "m-1's ask is resolved.",
            "op_id": "m-2", "supersedes": ["messages/m-1"]})   # missing .md normalized at send
        inbox7b = payload(await client.call_tool("imp_check",
            {"instance_id": "research-7", "unread_only": False}))["messages"]
        by_path = {m["path"]: m for m in inbox7b}
        assert "messages/m-1.md" in by_path, "flat-with-tombstones: the superseded message stays visible"
        assert by_path["messages/m-1.md"]["superseded_by"] == "messages/m-2.md", inbox7b
        assert by_path["messages/m-2.md"]["supersedes"] == ["messages/m-1.md"], inbox7b
        await client.call_tool("imp_mark_read", {"instance_id": "research-7", "message_path": "messages/m-2.md"})
        print("feature C: inbox tombstone resolved", {p: m["superseded_by"] for p, m in by_path.items()})

        # FEATURE C security (review finding 1): a DIFFERENT sender cannot tombstone m-1 (recto's, not
        # research-2's) — the supersedes edge is honored only when superseding + superseded share an author
        await client.call_tool("imp_send", {"sender": "recto", "recipients": ["research-7"],
            "subject": "spoof attempt — supersedes another sender's live message", "body": "should not tombstone m-1",
            "op_id": "m-3", "supersedes": ["messages/m-1"]})
        inbox7c = payload(await client.call_tool("imp_check",
            {"instance_id": "research-7", "unread_only": False}))["messages"]
        # m-1 is research-2's and was legitimately retired by research-2's m-2 — the recto edge must NOT
        # be what tombstones it; and if research-2 had NOT superseded it, recto could not either
        m1 = {m["path"]: m for m in inbox7c}["messages/m-1.md"]
        assert m1["superseded_by"] == "messages/m-2.md", "same-author edge stands; cross-author m-3 ignored"
        assert "messages/m-3.md" not in [m["superseded_by"] for m in inbox7c], "no cross-author tombstone"
        await client.call_tool("imp_mark_read", {"instance_id": "research-7", "message_path": "messages/m-3.md"})
        print("feature C security: cross-sender supersedes rejected")

        # the bug fix: read-state lives in the audit log, so a reindex must NOT wipe it
        reindex_from_git(store, index, emb)
        after_reindex = payload(await client.call_tool("imp_flags", {"instance_id": "research-7"}))
        # the declared supersedes-edge survives the reindex too — it rides the envelope in git
        inbox7c = payload(await client.call_tool("imp_check",
            {"instance_id": "research-7", "unread_only": False}))["messages"]
        assert {m["path"]: m for m in inbox7c}["messages/m-1.md"]["superseded_by"] == "messages/m-2.md", \
            "the inbox tombstone must survive a reindex"
        ok, bad = audit.verify()
        print("after reindex -> imp_flags r-7:", after_reindex, "| audit:", audit.count(), "verify:", (ok, bad))

        # authz seam: a message via kip_commit is denied (use imp_send), and the denial is audit-logged
        res = await client.call_tool("kip_commit", {"instance_id": "research-2", "domain": "messages",
                                                    "slug": "x", "body": "y", "op_id": "op-deny"})
        denied = bool(getattr(res, "isError", False))
        denial_logged = any(e["outcome"] == "denied" for e in audit.events())
        print("kip_commit into messages/ denied:", denied, "| denial audit-logged:", denial_logged)

        # ---- assertions ----
        paths = [h["path"] for h in allhits]
        assert "practice/durability-notes.md" in paths and "practice/no-silent-loss.md" in paths
        assert "messages/m-1.md" not in paths
        assert paths.index("practice/durability-notes.md") < paths.index("practice/scaling-notes.md")
        assert [h["path"] for h in canon_only] == ["practice/no-silent-loss.md"]
        assert all(h["author"] == "research-7" for h in mine7)
        assert [e["path"] for e in mp["entries"]] == ["practice/durability-notes.md"]
        assert mp["entries"][0]["title"], "the listing pointer carries the entry's title from the index"
        assert "Notes on durability" in got["text"]
        assert cp["conflicts"] is False and ps["status"] == "pending"
        assert flag7["unread"] == 1 and after["unread"] == 0
        assert len(recto) == 1
        assert after_reindex["unread"] == 0, "read-state must survive a reindex (it lives in the audit log)"
        assert ok and audit.count() >= 4, "writes were audit-logged and the chain verifies"
        assert denied and denial_logged, "authz seam denies + logs a message sent via kip_commit"
        print("\nOK -- full loop verified end to end through MCP (audit-logged; read-state survives reindex; authz seam active).")


anyio.run(main)
