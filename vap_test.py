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
        assert HORIZON in vf[0]["horizon"], "the excluded-from-search horizon surfaces via vap_for"

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
