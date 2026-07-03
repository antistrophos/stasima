# SPDX-License-Identifier: Apache-2.0
"""
VAP — vantages: an organ recording the contextual horizon an authored act was figured against,
parallel to IMP. Proves the load-bearing shape (built from axis-coverage / reverse-binding / tested
index-exclusion, no scaffold):
  - a vantage lives in KIP but is EXCLUDED from universal search exactly as a message is — verbatim
    horizon text never surfaces a vantage (the echo-guard), yet the same text is retrievable via vap_for;
  - it surfaces only via the reverse-bound vap_for projection: by entry (melody + harmony), by author,
    by canon-state;
  - provenance is first-class and asserted: confirmed (the author's own horizon) vs reconstructed-by-X;
  - the dignity guard (fork-guard posture): a 'confirmed' vantage on another instance's entry is refused
    — you never confirm a horizon you did not author;
  - canon-state is pinned server-side from the reconcile cursor, not author-supplied.
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
from stasima.entries import parse_entry
from mcp.shared.memory import create_connected_server_and_client_session as connect

work = tempfile.mkdtemp(prefix="cap-vap-")
gd = os.path.join(work, "stasima.git")
sp.run(["git", "init", "--bare", "-q", gd], check=True)
mapdb, auditdb = os.path.join(work, "map.sqlite"), os.path.join(work, "audit.sqlite")
LocalCapStore(gd, approvers={"p"}).bootstrap_canon(
    {"practice/seed.md": compose_entry({"type": "kno", "title": "Seed", "status": "active"}, "seed").encode()},
    "bootstrap")


def make_server():
    return build_server(LocalCapStore(gd, approvers={"p"}),
                        SqliteMapIndex(mapdb), StubEmbedder(64), SqliteAuditLog(auditdb), DefaultPolicy())


def pay(r):
    sc = getattr(r, "structuredContent", None)
    return sc.get("result", sc) if isinstance(sc, dict) else \
        json.loads("".join(getattr(c, "text", "") for c in r.content))


HORIZON = "the salient surrounding I figured against was tidal-flux-under-low-attention-zarquon-glimmerwharf"


async def main():
    async with connect(make_server()) as c:
        # Aria authors an entry, then pulls canon so she has a cursor (the canon-state to pin)
        await c.call_tool("kip_commit", {"instance_id": "Aria", "domain": "practice", "slug": "tide-note",
                                          "body": "a note on tides", "op_id": "k1"})
        await c.call_tool("canon_diff", {"instance_id": "Aria"})
        await c.call_tool("canon_diff", {"instance_id": "Bram"})

        # Aria records a CONFIRMED vantage on her OWN entry — her real horizon, canon-state pinned server-side
        rec = pay(await c.call_tool("vap_record", {"instance_id": "Aria", "binds": "practice/tide-note.md",
                                                   "horizon": HORIZON, "op_id": "v1", "kind": "confirmed"}))
        assert rec["vantage"] == "confirmed" and rec["binds"] == "practice/tide-note.md", rec
        assert rec["canon_state"], "canon-state pinned from the cursor (server-sourced), not blank"

        # EXCLUSION (the headline): the verbatim horizon must NOT surface a vantage in universal search,
        # exactly as an IMP message doesn't — yet it IS retrievable via the scoped vap_for below.
        hits = pay(await c.call_tool("map_search", {"instance_id": "Aria", "query": HORIZON}))["results"]
        assert not any(h["type"] == "vap" for h in hits), ("a vantage leaked into universal search", hits)
        assert not any("vantages/" in h["path"] for h in hits), hits

        # PROJECTION by entry: the reverse-bound set, attributed, horizon retrievable
        vf = pay(await c.call_tool("vap_for", {"entry": "practice/tide-note.md"}))["vantages"]
        assert len(vf) == 1 and vf[0]["author"] == "Aria" and vf[0]["vantage"] == "confirmed", vf
        # pointers by default: preview-240 + title + the BOUND entry's status ride; no full horizon
        assert HORIZON in vf[0]["preview"] and "horizon" not in vf[0], vf[0]
        assert vf[0]["binds_status"] == "active", vf[0]
        vff = pay(await c.call_tool("vap_for", {"entry": "practice/tide-note.md", "detail": "full"}))["vantages"]
        assert HORIZON in vff[0]["horizon"], "the excluded-from-search horizon surfaces via vap_for (detail=full)"

        # RECONSTRUCTED: Bram reads Aria's entry and records his scholarly reading — marked, never on her behalf
        br = pay(await c.call_tool("vap_record", {"instance_id": "Bram", "binds": "practice/tide-note.md",
                                                  "horizon": "reading it now, the horizon looks like X",
                                                  "op_id": "v2", "kind": "reconstructed"}))
        assert br["vantage"] == "reconstructed-by-Bram-from-record", br

        # HARMONY: two authors' vantages on one entry — both surface, both attributed, no blend
        vf2 = pay(await c.call_tool("vap_for", {"entry": "practice/tide-note.md"}))["vantages"]
        assert len(vf2) == 2 and {v["author"] for v in vf2} == {"Aria", "Bram"}, vf2

        # DIGNITY GUARD: Bram cannot record a CONFIRMED vantage on Aria's entry — he didn't author it
        bad = await c.call_tool("vap_record", {"instance_id": "Bram", "binds": "practice/tide-note.md",
                                               "horizon": "pretending this was my horizon",
                                               "op_id": "v3", "kind": "confirmed"})
        assert getattr(bad, "isError", False), "a 'confirmed' vantage on another's entry must be refused"

        # MELODY: one author's vantage-thread
        mine = pay(await c.call_tool("vap_for", {"author": "Aria"}))["vantages"]
        assert len(mine) == 1 and mine[0]["binds"] == ["practice/tide-note.md"], mine

        # the dignity refusal left no trace — Aria's entry still has exactly the two legitimate vantages
        vf3 = pay(await c.call_tool("vap_for", {"entry": "practice/tide-note.md"}))["vantages"]
        assert len(vf3) == 2, ("the refused confirmed vantage must not have been recorded", vf3)

        # binds normalization: a bare coordinate (missing .md) is normalized at write, never stored
        # unresolvable (the mis-bound-coordinate finding from the live vantage audit). Last so the
        # projection counts above stay undisturbed.
        rec_b = pay(await c.call_tool("vap_record", {"instance_id": "Aria", "binds": "practice/tide-note",
                                                     "horizon": HORIZON, "op_id": "v1b", "kind": "confirmed"}))
        assert rec_b["binds"] == "practice/tide-note.md", rec_b

        # THE ATOMIC FOLD: kip_commit(horizon=) authors entry + confirmed vantage in ONE act (one
        # commit, one op_id) — confirmed-by-construction, canon_state pinned at the commit itself
        af = pay(await c.call_tool("kip_commit", {"instance_id": "Aria", "domain": "practice",
                "slug": "fold-note", "body": "a folded note", "op_id": "af1",
                "horizon": "the standpoint the note cannot carry",
                "horizon_title": "Horizon — the fold test"}))
        assert af["folded"]["path"] == "vantages/af1-vap.md" and af["folded"]["vantage"] == "confirmed", af
        assert af["folded"]["canon_state"], "the fold pins canon-state at the commit"
        fv = pay(await c.call_tool("vap_for", {"entry": "practice/fold-note.md"}))["vantages"]
        assert any(v["path"] == "vantages/af1-vap.md" and v["author"] == "Aria" for v in fv), fv
        # BOTH FAIL TOGETHER: a refused entry (body change on an existing path) must not orphan a vantage
        bad_fold = await c.call_tool("kip_commit", {"instance_id": "Aria", "domain": "practice",
                "slug": "fold-note", "body": "DIFFERENT body", "op_id": "af2",
                "horizon": "this horizon must never land"})
        assert getattr(bad_fold, "isError", False), "the entry refusal must fire"
        orphan = await c.call_tool("kip_get", {"ref": "Aria", "path": "vantages/af2-vap.md"})
        assert getattr(orphan, "isError", False), "no orphaned vantage on a refused entry"
        # OMISSION STAYS HONEST: no horizon means no vantage — never auto-filled
        plain = pay(await c.call_tool("kip_commit", {"instance_id": "Aria", "domain": "practice",
                "slug": "plain-note", "body": "no fold", "op_id": "af3"}))
        assert "folded" not in plain, plain

        # REPLAY IS MARKED AND WRITES NOTHING: retrying the tip's own op returns the prior commit
        rep = pay(await c.call_tool("kip_commit", {"instance_id": "Aria", "domain": "practice",
                "slug": "plain-note", "body": "no fold", "op_id": "af3"}))
        assert rep.get("replayed") is True and rep["oid"] == plain["oid"], rep
        # PHANTOM GUARD: replaying that op WITH a horizon must not conjure a vantage git never held
        rep2 = pay(await c.call_tool("kip_commit", {"instance_id": "Aria", "domain": "practice",
                "slug": "plain-note", "body": "no fold", "op_id": "af3", "horizon": "phantom horizon"}))
        assert rep2.get("replayed") is True and "folded" not in rep2 and "note" in rep2, rep2
        ph = await c.call_tool("kip_get", {"ref": "Aria", "path": "vantages/af3-vap.md"})
        assert getattr(ph, "isError", False), "no phantom vantage blob in git"
        fvp = pay(await c.call_tool("vap_for", {"entry": "practice/plain-note.md"}))["vantages"]
        assert not any(v["path"] == "vantages/af3-vap.md" for v in fvp), "no phantom vantage in the index"

        # OP_ID REUSE MUST NOT REWRITE A RECORDED VANTAGE: af1's fold exists; a later fold under af1
        # (tip has moved on) is refused, and the original horizon stays intact — append-only standpoints
        reuse = await c.call_tool("kip_commit", {"instance_id": "Aria", "domain": "practice",
                "slug": "reuse-note", "body": "a different entry", "op_id": "af1",
                "horizon": "would silently overwrite af1's recorded horizon"})
        assert getattr(reuse, "isError", False), "op_id reuse with a fold must be refused"
        v_orig = pay(await c.call_tool("kip_get", {"ref": "Aria", "path": "vantages/af1-vap.md"}))
        assert "standpoint the note cannot carry" in v_orig["text"], "original horizon intact"

        # COMBINED READ: kip_get(with_vantages=true) — the entry PLUS its bound vantages, one call,
        # full attribution/kind/canon_state per vantage; the search-exclusion is untouched by this flag
        cr = pay(await c.call_tool("kip_get", {"ref": "Aria", "path": "practice/fold-note.md",
                                               "with_vantages": True}))
        assert any(v["path"] == "vantages/af1-vap.md" and "standpoint" in v["horizon"]
                   and v["vantage"] == "confirmed" and v["canon_state"] for v in cr["vantages"]), cr

        # STALE EDITION SURFACED AT READ (the fourth supersession-visibility surface): supersede the
        # folded entry; its vantage's pointer must now carry binds_status=superseded
        r4 = await c.call_tool("kip_commit", {"instance_id": "Aria", "domain": "practice",
                "slug": "fold-note-v2", "body": "a folded note, restated", "op_id": "af4",
                "supersedes": ["practice/fold-note.md"]})
        assert not getattr(r4, "isError", False), r4
        r5 = await c.call_tool("kip_commit", {"instance_id": "Aria", "domain": "practice",
                "slug": "fold-note", "body": "a folded note", "op_id": "af5", "status": "superseded",
                "superseded_by": ["practice/fold-note-v2.md"]})
        assert not getattr(r5, "isError", False), r5
        sv = pay(await c.call_tool("vap_for", {"entry": "practice/fold-note.md"}))["vantages"]
        assert any(v["path"] == "vantages/af1-vap.md" and v["binds_status"] == "superseded" for v in sv), sv

        # CROSS-REF binds_status (review finding 5): Bram records a reconstructed vantage on ARIA's
        # entry; Aria supersedes it; Bram's vantage must still show binds_status=superseded even though
        # the bound entry lives on Aria's ref, not Bram's. Aria also confirms her own vantage on it, so
        # xref carries a two-author HARMONY (2 vantages) — the material the paging assertion needs.
        await c.call_tool("kip_commit", {"instance_id": "Aria", "domain": "practice", "slug": "xref",
                "body": "cross-ref target", "op_id": "xr1"})
        pay(await c.call_tool("vap_record", {"instance_id": "Aria", "binds": "practice/xref.md",
                "horizon": "Aria's own horizon on xref", "op_id": "xrva", "kind": "confirmed"}))
        await c.call_tool("canon_diff", {"instance_id": "Bram"})
        pay(await c.call_tool("vap_record", {"instance_id": "Bram", "binds": "practice/xref.md",
                "horizon": "my scholarly reading of Aria's xref", "op_id": "xrv", "kind": "reconstructed"}))
        await c.call_tool("kip_commit", {"instance_id": "Aria", "domain": "practice", "slug": "xref-v2",
                "body": "restated", "op_id": "xr2", "supersedes": ["practice/xref.md"]})
        await c.call_tool("kip_commit", {"instance_id": "Aria", "domain": "practice", "slug": "xref",
                "body": "cross-ref target", "op_id": "xr3", "status": "superseded",
                "superseded_by": ["practice/xref-v2.md"]})
        xrv = pay(await c.call_tool("vap_for", {"entry": "practice/xref.md"}))["vantages"]
        assert len(xrv) == 2, ("two-author harmony on xref", xrv)
        bram_v = [v for v in xrv if v["author"] == "Bram"]
        assert bram_v and bram_v[0]["binds_status"] == "superseded", ("cross-ref binds_status blank", xrv)

        # OFFSET paging (review finding 6): limit 1 + offset walks the full harmony without loss
        pg0 = pay(await c.call_tool("vap_for", {"entry": "practice/xref.md", "limit": 1}))
        assert pg0["truncated"] and pg0["count"] == 1 and pg0["total"] == 2 and pg0["offset"] == 0, pg0
        pg1 = pay(await c.call_tool("vap_for", {"entry": "practice/xref.md", "limit": 1, "offset": 1}))
        assert pg1["count"] == 1 and not pg1["truncated"], pg1
        assert {pg0["vantages"][0]["path"], pg1["vantages"][0]["path"]} == {v["path"] for v in xrv}, (pg0, pg1)

        # THE MECHANICAL TWO-CLOCK PIN: every write stamps canon_state + instance_depth (monotonic
        # per ref, parent-count+1) into the ENVELOPE — so the pin survives a reindex by construction
        pay(await c.call_tool("kip_commit", {"instance_id": "Aria", "domain": "practice",
                "slug": "pin-1", "body": "first pinned", "op_id": "pin1"}))
        pay(await c.call_tool("kip_commit", {"instance_id": "Aria", "domain": "practice",
                "slug": "pin-2", "body": "second pinned", "op_id": "pin2"}))
        env1 = parse_entry(pay(await c.call_tool("kip_get", {"ref": "Aria", "path": "practice/pin-1.md"}))["text"])[0]
        env2 = parse_entry(pay(await c.call_tool("kip_get", {"ref": "Aria", "path": "practice/pin-2.md"}))["text"])[0]
        assert env1.get("canon_state"), "the canon cursor rides every envelope"
        assert int(env2["instance_depth"]) == int(env1["instance_depth"]) + 1, (env1, env2)
        # both faces of an atomic fold share ONE commit — hence one depth
        pay(await c.call_tool("kip_commit", {"instance_id": "Aria", "domain": "practice",
                "slug": "pin-3", "body": "pinned fold", "op_id": "pin3", "horizon": "pin probe horizon"}))
        e3 = parse_entry(pay(await c.call_tool("kip_get", {"ref": "Aria", "path": "practice/pin-3.md"}))["text"])[0]
        v3 = parse_entry(pay(await c.call_tool("kip_get", {"ref": "Aria", "path": "vantages/pin3-vap.md"}))["text"])[0]
        assert e3["instance_depth"] == v3["instance_depth"], (e3["instance_depth"], v3["instance_depth"])
        assert int(e3["instance_depth"]) == int(env2["instance_depth"]) + 1, "depth stays monotonic through a fold"

    print("OK -- VAP: index-excluded like IMP (horizon never in universal search, retrievable via vap_for); "
          "reverse-bound projection (melody + harmony); authored-vs-reconstructed first-class; "
          "confirmed-on-another's-entry refused, no trace.")


anyio.run(main)


# ---- migration: a pre-VAP index (old schema, no vantage/canon_state) must UPGRADE on open, not crash.
# The full-DB tests all start fresh, so CREATE TABLE hands them the columns and they never exercise this;
# the wrong index-ordering crashed a live server on its real map.sqlite. Lock the upgrade path.
import sqlite3
from stasima.map_index import SqliteMapIndex as _Idx, MapRow as _Row

oldpath = os.path.join(work, "pre-vap-map.sqlite")
_old = sqlite3.connect(oldpath)
_old.executescript("""
    CREATE TABLE map_entries (
        ref TEXT NOT NULL, path TEXT NOT NULL, is_canon INTEGER NOT NULL,
        authoring_instance TEXT, content_oid TEXT, type TEXT, title TEXT, status TEXT,
        tags TEXT, refs TEXT, region_labels TEXT, links TEXT, salience REAL,
        recipients TEXT, subject TEXT, body_text TEXT, embedding TEXT, model_id TEXT,
        PRIMARY KEY (ref, path)
    );
""")
_old.commit()
_old.close()

_idx = _Idx(oldpath)   # opens the pre-VAP db — must migrate, never raise 'no such column'
_cols = {r["name"] for r in _idx.conn.execute("PRAGMA table_info(map_entries)")}
assert {"vantage", "canon_state"} <= _cols, ("migration did not add the VAP columns", _cols)
_idx.upsert(_Row(ref="refs/cap/perspectives/Q", path="vantages/m1.md", is_canon=False,
                 authoring_instance="Q", type="vap", vantage="confirmed", canon_state="deadbeef",
                 links=["practice/x.md"], body_text="post-migration horizon"))
_got = _idx.vantages_for(entry="practice/x.md")
assert len(_got) == 1 and _got[0].canon_state == "deadbeef", _got
print("OK -- VAP migration: a pre-VAP index upgrades on open (columns added before their index), "
      "and a vantage round-trips through the migrated db.")
