# SPDX-License-Identifier: Apache-2.0
"""
Entry search: the word leg, the merge with the meaning leg, and the index's own upkeep.

The first block is Repose's finding as a fixture (canon ::21, 2026-11): a seat that knows an
entry's NAME must find it. Under the stub embedder alone, none of seven name queries returned the
named entry. Proven here:

  1. a name in a title, a tag, or a path ranks first (match='name'); every-word and any-word follow;
  2. scope, type, and tags filter; tags alone list; messages and vantages never surface;
  3. one body held on several refs is one result, canon's row first, with its holders;
  4. a body canon has retired does not return through an unflipped copy, unless asked for;
  5. the meaning leg merges by rank, a name still leads, and the relevance floor is the meaning
     leg's alone (withheld with a count; include_weak returns them);
  6. the index keeps itself: an index from before this change fills on open, a replaced entry leaves
     no old words, a writer running older code still feeds it, and clear() empties it;
  7. without FTS5 the search still answers, from the embedder alone, and says so;
  8. the wire: `tags` in the schema, `query` optional, refusals that name the fix.
"""
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anyio
from mcp.client import Client as connect
from _testkit import fresh_repo, payload, is_err, err_text
from stasima import lexical
from stasima.cap_server import build_server
from stasima.local_capstore import LocalCapStore
from stasima.audit_log import SqliteAuditLog
from stasima.map_index import SqliteMapIndex, StubEmbedder, Embedder, index_entry, body_digest, _normalize
from stasima.search import find_entries

CANON, P = "refs/heads/main", "refs/cap/perspectives/"


def put(idx, emb, ref, path, title, body, *, author="", tags=(), type="kno", status="active"):
    index_entry(idx, emb, ref=ref, path=path, is_canon=(ref == CANON),
                authoring_instance=author or ref.rsplit("/", 1)[-1], content_oid="0" * 40,
                envelope={"type": type, "title": title, "status": status, "tags": list(tags)}, body=body)


def corpus(idx, emb):
    put(idx, emb, CANON, "argot/legenda.md", "legenda", "A canon small enough that one reader takes in all of it.", author="Hesper", type="arg")
    put(idx, emb, CANON, "technical/seal-banns-objection-window-v4.md", "The banns, v4 — the objection window before a seal",
        "Before a canon is sealed, a call opens a window in which seats may object.", author="epode")
    put(idx, emb, CANON, "meta/log/1d.md", "::1D — the cluster lands", "Fourteen items, the banns among them, land as one.", author="epode", type="log")
    put(idx, emb, CANON, "technical/canon-legenda-criterion.md", "The readable-entire criterion",
        "Each level of canon stays small enough to be read whole; past that it splits.", author="Hesper")
    put(idx, emb, P + "Compass", "manual/14.md", "[14] Mutually Assured Construction [1] — Clark concordance",
        "Productive tension between distinct perspectives generates material neither could produce alone.",
        tags=["mac", "mutually-assured-construction"])
    put(idx, emb, P + "Recto", "state/27.md", "Recto ::27 — the MAC entries mapped", "The mutually assured construction entries, in order.")
    put(idx, emb, P + "epode", "practice/rehearsal-note.md", "A rehearsal note", "The the the of of and a a to to in in is is it it.")
    put(idx, emb, P + "epode", "practice/tides.md", "Tides", "Durability means never losing committed work.", tags=["mac"])
    # the unsearchable types, each carrying a name another entry is found by
    put(idx, emb, P + "Recto", "messages/m1.md", "legenda", "legenda legenda the banns", type="msg")
    put(idx, emb, P + "Recto", "vantages/v1.md", "vantage on the banns", "the banns, mutually assured construction", type="vap")
    # one body on two refs
    same = "The retro map lands whole: both editions, so old citations resolve."
    put(idx, emb, CANON, "meta/log/1b.md", "::1B — the retro map", same, author="epode", type="log")
    put(idx, emb, P + "epode", "meta/log/1b.md", "::1B — the retro map", same, type="log")
    # a body canon retired, with an unflipped copy on its author's branch
    old = "The two-clock conventions, third edition: the mirror field is optional forever."
    put(idx, emb, CANON, "meta/conventions/two-clock-ticks-v3.md", "The two-clock conventions, v3", old, author="Hesper", status="superseded")
    put(idx, emb, P + "Hesper", "meta/conventions/two-clock-ticks-v3.md", "The two-clock conventions, v3", old)
    put(idx, emb, CANON, "meta/conventions/two-clock-ticks-v4.md", "The two-clock conventions, v4 — the join",
        "The two-clock conventions, fourth edition: a seat's first write is its ::1.", author="epode")


def paths(answer):
    return [r["path"] for r in answer["results"]]


def rank(answer, path):
    return next((i for i, r in enumerate(answer["results"], 1) if r["path"] == path), None)


idx, stub = SqliteMapIndex(":memory:"), StubEmbedder(64)
assert idx.fts, "this SQLite build has no FTS5 — the suite's platforms all do; the word leg is untested without it"
corpus(idx, stub)
find = lambda q="", **kw: find_entries(idx, stub, q, seat=kw.pop("seat", "Repose"), **kw)

# ---- 1. names (Repose's table)
a = find("Mutually Assured Construction")
assert a["mode"] == "words" and rank(a, "manual/14.md") == 1 and a["results"][0]["match"] == "name", a
a = find("legenda")
assert rank(a, "argot/legenda.md") == 1 and a["results"][0]["match"] == "name", a
assert rank(find("legenda", scope="canon"), "argot/legenda.md") == 1
a = find("the banns")
assert rank(a, "technical/seal-banns-objection-window-v4.md") == 1 and a["results"][0]["match"] == "name", a
assert rank(find("the banns", scope="canon"), "technical/seal-banns-objection-window-v4.md") == 1
a = find("seal-banns-objection-window-v4")                       # a slug is a name too
assert rank(a, "technical/seal-banns-objection-window-v4.md") == 1 and a["results"][0]["match"] == "name", a
a = find("mutually assured construction integrative power naming the seat")
assert rank(a, "manual/14.md") is not None and rank(a, "manual/14.md") <= 3, a
a = find("productive tension between distinct perspectives generates material neither could produce alone")
assert rank(a, "manual/14.md") == 1 and a["results"][0]["match"] == "all-words", a
assert "Productive tension" in a["results"][0]["preview"], a["results"][0]["preview"]     # the passage that matched
a = find("durability of tides and other things nobody wrote")
assert rank(a, "practice/tides.md") == 1 and a["results"][0]["match"] == "some-words", a
print("1. names: a title, a tag, a path, and a slug each rank their entry first; every-word and any-word follow")

# ---- 2. filters, and what never surfaces
for q in ("legenda", "the banns", "mutually assured construction"):
    assert not any(r["type"] in ("msg", "vap") for r in find(q, limit=50)["results"]), q
assert paths(find("legenda", type="arg")) == ["argot/legenda.md"]
assert paths(find("construction", scope="mine", seat="Compass")) == ["manual/14.md"]
assert paths(find("tension", tags=["MAC"])) == ["manual/14.md"]                     # tags compare without case
assert sorted(paths(find(tags=["mac"]))) == ["manual/14.md", "practice/tides.md"]   # tags alone list
assert find(tags=["mac"])["results"][0]["match"] == "tag"
assert paths(find(tags=["mac", "mutually-assured-construction"])) == ["manual/14.md"]
assert paths(find(tags=["m"])) == [] and "tags" in find(tags=["m"])["note"]          # a tag is whole, never a prefix
empty = find("zzzqqq")
assert empty["results"] == [] and "words, not meaning" in empty["note"], empty
print("2. scope, type, tags filter; tags alone list; messages and vantages never surface; an empty answer says why")

# ---- 3. one body, one result
a = find("retro map")
hits = [r for r in a["results"] if r["path"] == "meta/log/1b.md"]
assert len(hits) == 1 and hits[0]["is_canon"] and hits[0]["holders"] == ["canon", "epode"], a
mine = find("retro map", scope="mine", seat="epode")["results"][0]
assert mine["path"] == "meta/log/1b.md" and "holders" in mine, mine                  # both rows are epode's
assert "holders" not in find("legenda")["results"][0]                                 # held once: no list
print("3. one body on two refs returns once, canon's row first, holders listed")

# ---- 4. canon decides whether a body it holds is live
a = find("two-clock conventions")
assert "meta/conventions/two-clock-ticks-v3.md" not in paths(a) and rank(a, "meta/conventions/two-clock-ticks-v4.md") == 1, a
a = find("two-clock conventions", include_superseded=True)
v3 = [r for r in a["results"] if r["path"] == "meta/conventions/two-clock-ticks-v3.md"]
assert len(v3) == 1 and v3[0]["status"] == "superseded" and v3[0]["is_canon"], a
print("4. a body canon retired stays out, unflipped copy and all; include_superseded shows it, marked")


# ---- 5. the meaning leg
class Concepts(Embedder):
    """A stand-in meaning model: three axes, each a set of words that mean one thing."""
    semantic, model_id, dim, score_floor = True, "concepts-3", 3, 0.0
    AXES = [{"durability", "losing", "committed", "work", "saved", "keep", "survives"},
            {"sealed", "seal", "object", "protest", "closing", "window", "banns"},
            {"tension", "perspectives", "construction", "disagreement"}]

    def embed(self, texts):
        return [_normalize([sum(w in ax for w in lexical.words(t)) + 0.01 for ax in self.AXES]) for t in texts]


sem_idx, sem = SqliteMapIndex(":memory:"), Concepts()
corpus(sem_idx, sem)
sfind = lambda q, **kw: find_entries(sem_idx, sem, q, seat="Repose", **kw)
a = sfind("what survives when something saved must keep")         # no word of the tides entry's body or title
top = a["results"][0]
assert a["mode"] == "words+meaning" and top["path"] == "practice/tides.md" and top["match"] == "meaning", a
assert top["similarity"] > 0.9, top
a = sfind("the banns")                                            # found by both legs: the name still leads
assert a["results"][0]["path"] == "technical/seal-banns-objection-window-v4.md" and a["results"][0]["match"] == "name", a
assert "similarity" in a["results"][0], a["results"][0]
a = sfind("protest before closing")                               # words find nothing; meaning does
assert a["results"] and a["results"][0]["path"] == "technical/seal-banns-objection-window-v4.md", a
sem.score_floor = 1.01                                             # above any cosine: every vector hit is weak
a = sfind("what survives when something saved must keep")
assert a["below_floor"] > 0 and all(r["match"] != "meaning" for r in a["results"]), a
assert sfind("zzzqqq")["note"].startswith(str(sfind("zzzqqq")["below_floor"])), sfind("zzzqqq")
a = sfind("what survives when something saved must keep", include_weak=True)
assert a["below_floor"] == 0 and a["results"][0]["path"] == "practice/tides.md", a
sem.score_floor = 0.0
print("5. meaning merges by rank: found without a shared word; a name still leads; the floor is the meaning leg's alone")

# ---- 6. the index keeps itself
work = tempfile.mkdtemp(prefix="stasima-search-")
db = os.path.join(work, "map.sqlite")
old = sqlite3.connect(db)                                          # an index from before this change
old.executescript("""CREATE TABLE map_entries (ref TEXT NOT NULL, path TEXT NOT NULL, is_canon INTEGER NOT NULL,
    authoring_instance TEXT, content_oid TEXT, type TEXT, title TEXT, status TEXT, tags TEXT, refs TEXT,
    supersedes TEXT, region_labels TEXT, links TEXT, salience REAL, recipients TEXT, subject TEXT, vantage TEXT,
    canon_state TEXT, instance_depth INTEGER, tick TEXT, thread TEXT, body_text TEXT, embedding TEXT, model_id TEXT,
    PRIMARY KEY (ref, path));""")
ins = ("INSERT OR REPLACE INTO map_entries (ref, path, is_canon, authoring_instance, type, title, status, tags, body_text, embedding) "
       "VALUES (?,?,?,?,?,?,?,?,?,?)")
old.execute(ins, (CANON, "argot/legenda.md", 1, "Hesper", "arg", "legenda", "active", "[]", "read entire", "[]"))
old.execute(ins, (P + "Recto", "messages/m1.md", 0, "Recto", "msg", "legenda", "active", "[]", "legenda", "[]"))
old.commit(); old.close()
up = SqliteMapIndex(db)
count = lambda i: (i.conn.execute("SELECT COUNT(*) FROM map_fts").fetchone()[0],
                   i.conn.execute("SELECT COUNT(*) FROM map_entries WHERE type NOT IN ('msg','vap')").fetchone()[0])
assert up.fts and count(up) == (1, 1), count(up)
assert up.conn.execute("SELECT body_hash FROM map_entries WHERE path='argot/legenda.md'").fetchone()[0] == body_digest("read entire")
assert paths(find_entries(up, stub, "legenda", seat="x")) == ["argot/legenda.md"]
put(up, stub, CANON, "argot/legenda.md", "renamed", "other words entirely", author="Hesper", type="arg")
assert paths(find_entries(up, stub, "read", seat="x")) == [] and count(up) == (1, 1)             # the old body's words are gone
assert paths(find_entries(up, stub, "renamed", seat="x")) == ["argot/legenda.md"]
legacy = sqlite3.connect(db)                                       # a process running older code: no pragma, old columns
legacy.execute(ins, (CANON, "argot/legenda.md", 1, "Hesper", "arg", "third title", "active", "[]", "third body", "[]"))
legacy.execute(ins, (P + "Recto", "practice/new.md", 0, "Recto", "kno", "written by old code", "active", "[]", "fresh", "[]"))
legacy.commit(); legacy.close()
assert paths(find_entries(up, stub, "written by old code", seat="x")) == ["practice/new.md"]     # the triggers fed it
assert paths(find_entries(up, stub, "renamed", seat="x")) == []                                  # the stale row cannot surface
assert paths(find_entries(up, stub, "third title", seat="x")) == ["argot/legenda.md"]
up.conn.close()
again = SqliteMapIndex(db)                                         # the next start levels the table
assert count(again) == (2, 2), count(again)
assert again.conn.execute("SELECT COUNT(*) FROM map_entries WHERE body_hash IS NULL OR body_hash=''").fetchone()[0] == 0
again.clear()
assert count(again) == (0, 0)
again.conn.close()
print("6. upkeep: an older index fills on open; a replace leaves no old words; older code still feeds it; clear() empties it")

# ---- 7. without FTS5
idx.fts = False
a = find("legenda")
assert a["mode"] == "approximate" and a["results"] and all(r["match"] == "approximate" for r in a["results"]), a
idx.fts = True
print("7. no FTS5: the embedder alone answers, and the mode says so")


# ---- 8. the wire
async def wire():
    w, gd = fresh_repo("stasima-search-wire-")
    store = LocalCapStore(gd, approvers={"practitioner"})
    server = build_server(store, SqliteMapIndex(":memory:"), StubEmbedder(64), SqliteAuditLog(":memory:"),
                          binding_mode="off", join_gate=False)
    async with connect(server) as c:
        tool = {t.name: t for t in (await c.list_tools()).tools}["entry_search"]
        props, required = tool.input_schema["properties"], tool.input_schema.get("required", [])
        assert "tags" in props and "query" not in required and "seat" in required, tool.input_schema
        assert tool.description.rstrip().endswith("Class: replica."), tool.description
        await c.call_tool("entry_write", {"seat": "Compass", "domain": "manual", "slug": "14", "op_id": "w1",
                                          "title": "Mutually Assured Construction", "tags": ["mac"],
                                          "body": "Productive tension between perspectives."})
        got = payload(await c.call_tool("entry_search", {"seat": "Repose", "query": "mutually assured construction"}))
        assert got["mode"] == "words" and got["results"][0]["path"] == "manual/14.md" and got["results"][0]["match"] == "name", got
        got = payload(await c.call_tool("entry_search", {"seat": "Repose", "tags": ["mac"]}))
        assert paths(got) == ["manual/14.md"], got
        r = await c.call_tool("entry_search", {"seat": "Repose", "query": "  ?! "})
        assert is_err(r) and "`query`" in err_text(r) and "`tags`" in err_text(r), err_text(r)
        r = await c.call_tool("entry_search", {"seat": "Repose", "query": "x", "scope": "everything"})
        assert is_err(r) and "'all', 'canon', or 'mine'" in err_text(r), err_text(r)
    print("8. the wire: tags in the schema, query optional, an empty question and an unknown scope refused with the fix")


anyio.run(wire)
print("\nOK -- entry search: names found, one body one result, canon decides liveness, legs merge by rank, the index keeps itself.")
