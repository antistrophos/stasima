# SPDX-License-Identifier: Apache-2.0
"""
Entry search: the word leg, the merge with the meaning leg, and the index's own upkeep.

The first block is Repose's finding as a fixture (canon ::21, 2026-11): a seat that knows an
entry's NAME must find it. Under the stub embedder alone, none of seven name queries returned the
named entry. Proven here:

  1. a name in a title, a tag, or a path ranks first (match='name'); every-word and any-word follow;
     a word in a title outranks the same word repeated in a body; the preview is the passage that
     matched; a query is read the way the tokenizer reads the entry, in any script or composition;
  2. scope, type, and tags filter; tags alone list; a tag of any script or punctuation filters and
     is a name; messages and vantages never surface; `limit` is the size of the answer;
  3. one entry held on several refs is one result, canon's row first, with its holders; two entries
     that share a body stay two, each under its own name;
  4. an entry canon has retired does not return through an unflipped copy, unless asked for; an
     entry moved by supersession is found at its live path; an empty answer says what was withheld;
  5. the meaning leg merges by rank, a name still leads, and the relevance floor is the meaning
     leg's alone (withheld with a count; include_weak returns them);
  6. an answer is full when the corpus can fill it: copies and retired editions that crowd the
     candidate pool do not shorten it;
  7. the index keeps itself: an index from before this change fills on open, a replaced entry leaves
     no old words, a writer running older code still feeds it and its rows obey rules 3 and 4
     before the next start, and clear() empties it;
  8. two searches at the same moment each get their own answer;
  9. without FTS5 the search still answers, from the embedder alone, and says so;
 10. the wire: `tags` in the schema, `query` optional, refusals that name the fix.
"""
import os
import sqlite3
import sys
import tempfile
import threading
import unicodedata

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
    # one entry on two refs
    same = "The retro map lands whole: both editions, so old citations resolve."
    put(idx, emb, CANON, "meta/log/1b.md", "::1B — the retro map", same, author="epode", type="log")
    put(idx, emb, P + "epode", "meta/log/1b.md", "::1B — the retro map", same, type="log")
    # an entry canon retired, with an unflipped copy on its author's branch
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
ask = lambda i, q="", **kw: find_entries(i, stub, q, seat=kw.pop("seat", "Repose"), **kw)

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

w = SqliteMapIndex(":memory:")
put(w, stub, CANON, "notes/a.md", "The window for an objection", "Plain text about nothing in particular, kept short.", author="epode")
put(w, stub, CANON, "notes/b.md", "Minutes of the day", "objection window, objection window, objection window: the minutes say it thrice.", author="epode")
filler = "Nothing in this opening stretch concerns the question. " * 8
put(w, stub, CANON, "notes/long.md", "A long note", filler + "Far below, the zephyrine clause finally appears. " + filler, author="epode")
a = ask(w, "objection window")                                   # in neither name as a phrase: the columns decide
assert paths(a)[:2] == ["notes/a.md", "notes/b.md"] and a["results"][0]["match"] == "all-words", a
a = ask(w, "zephyrine")
assert "zephyrine" in a["results"][0]["preview"] and "zephyrine" not in (filler + "Far below")[:160], a

u = SqliteMapIndex(":memory:")
put(u, stub, CANON, "notes/city.md", "İstanbul notes", "A travel log.", author="epode")
put(u, stub, CANON, "notes/cv.md", "Résumé conventions", "How the page is laid out.", author="epode")
for q in ("İstanbul", "istanbul", "ISTANBUL"):
    assert paths(ask(u, q)) == ["notes/city.md"], q.encode("unicode_escape")
for q in ("résumé", unicodedata.normalize("NFD", "résumé"), "resume", "RÉSUMÉ"):
    assert paths(ask(u, q)) == ["notes/cv.md"], q.encode("unicode_escape")
print("1. names: a title, a tag, a path, and a slug each rank their entry first; every-word and any-word follow; "
      "a title outranks a body; the preview is the passage; any script or composition reads the same")

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
assert len(find("canon")["results"]) >= 3 and len(find("canon", limit=2)["results"]) == 2    # limit is the answer's size

t = SqliteMapIndex(":memory:")
put(t, stub, P + "Compass", "notes/beans.md", "Roast log", "Espresso notes.", tags=["café", "plain"])
put(t, stub, P + "Compass", "notes/chorus.md", "Ode", "The second movement.", tags=["στάσιμον"])
put(t, stub, P + "Compass", "notes/quote.md", "Quoted", "A third thing.", tags=['say "hi"', "back\\slash", "100%_done!"])
assert paths(ask(t, tags=["café"])) == ["notes/beans.md"] and paths(ask(t, tags=["CAFÉ"])) == ["notes/beans.md"]
assert paths(ask(t, "espresso", tags=["café"])) == ["notes/beans.md"]
assert paths(ask(t, tags=["στάσιμον"])) == ["notes/chorus.md"]
for tag in ('say "hi"', "back\\slash", "100%_done!"):
    assert paths(ask(t, tags=[tag])) == ["notes/quote.md"], tag
assert paths(ask(t, tags=["caf"])) == [] and paths(ask(t, tags=["100"])) == []      # still whole tags
a = ask(t, "στάσιμον")                                                               # a tag is a name in any script
assert paths(a) == ["notes/chorus.md"] and a["results"][0]["match"] == "name", a
assert paths(ask(t, "café")) == ["notes/beans.md"]
print("2. scope, type, tags filter; tags alone list; a tag of any script filters and is a name; messages and "
      "vantages never surface; limit holds; an empty answer says why")

# ---- 3. one entry, one result
a = find("retro map")
hits = [r for r in a["results"] if r["path"] == "meta/log/1b.md"]
assert len(hits) == 1 and hits[0]["is_canon"] and hits[0]["holders"] == ["canon", "epode"], a
mine = find("retro map", scope="mine", seat="epode")["results"][0]
assert mine["path"] == "meta/log/1b.md" and "holders" in mine, mine                  # both rows are epode's
assert "holders" not in find("legenda")["results"][0]                                 # held once: no list

e = SqliteMapIndex(":memory:")
shared = "Notes every seat carries the same."
put(e, stub, P + "Recto", "practice/notes.md", "Shared notes", shared)                # a carried copy
put(e, stub, P + "epode", "practice/notes.md", "Shared notes", shared)
put(e, stub, CANON, "practice/notes.md", "Shared notes", shared, author="epode")
put(e, stub, P + "Vesper", "practice/notes.md", "Shared notes", shared, type="msg")   # never a holder
r = ask(e, "shared notes")["results"]
assert len(r) == 1 and r[0]["is_canon"] and r[0]["holders"] == ["canon", "Recto", "epode"], r
put(e, stub, CANON, "practice/beta-checkpoint.md", "Beta checkpoint", "Nothing to report.", author="epode", type="log")
put(e, stub, P + "Recto", "practice/gamma-checkpoint.md", "Gamma checkpoint", "Nothing to report.")
g = ask(e, "gamma checkpoint")["results"][0]                                          # same body, another entry
assert (g["path"], g["title"], g["is_canon"], g["type"]) == ("practice/gamma-checkpoint.md", "Gamma checkpoint", False, "kno"), g
assert "holders" not in g, g
assert sorted(paths(ask(e, "nothing to report"))) == ["practice/beta-checkpoint.md", "practice/gamma-checkpoint.md"]
assert paths(ask(e, "nothing to report", type="kno")) == ["practice/gamma-checkpoint.md"]
twice = "One body under two envelopes."
put(e, stub, CANON, "practice/typed.md", "Typed note", twice, author="epode", type="log")
put(e, stub, P + "epode", "practice/typed.md", "Typed note", twice, tags=["draft"])
k = ask(e, "typed note")["results"][0]                                                # canon's row, in canon's fields
assert (k["is_canon"], k["type"], k["holders"]) == (True, "log", ["canon", "epode"]), k
for kw in ({"type": "kno"}, {"tags": ["draft"]}):                                     # canon's row does not fit the ask
    k = ask(e, "typed note", **kw)["results"][0]
    assert (k["ref"], k["is_canon"], k["type"]) == (P + "epode", False, "kno"), (kw, k)
print("3. one entry on several refs returns once, canon's row first, holders listed; two entries that share a body stay two")

# ---- 4. canon decides whether an entry it holds is live
a = find("two-clock conventions")
assert "meta/conventions/two-clock-ticks-v3.md" not in paths(a) and rank(a, "meta/conventions/two-clock-ticks-v4.md") == 1, a
a = find("two-clock conventions", include_superseded=True)
v3 = [r for r in a["results"] if r["path"] == "meta/conventions/two-clock-ticks-v3.md"]
assert len(v3) == 1 and v3[0]["status"] == "superseded" and v3[0]["is_canon"], a

c4 = SqliteMapIndex(":memory:")
moved = "A write is durable once the store has synced it to the disk."
put(c4, stub, CANON, "practice/durability-rule.md", "The durability rule", moved, author="epode", status="superseded")
put(c4, stub, CANON, "technical/durability-rule.md", "The durability rule", moved, author="epode")
put(c4, stub, P + "epode", "practice/durability-rule.md", "The durability rule", moved)      # the unflipped copy
put(c4, stub, P + "epode", "technical/durability-rule.md", "The durability rule", moved)
for kw in ({}, {"scope": "canon"}, {"scope": "mine", "seat": "epode"}):                      # a move by supersession
    a = ask(c4, "durability rule", **kw)
    assert paths(a) == ["technical/durability-rule.md"], (kw, a)
    assert a["results"][0]["is_canon"] and a["results"][0]["status"] == "active", (kw, a)
assert paths(ask(c4, "synced to the disk")) == ["technical/durability-rule.md"]
a = ask(c4, "durability rule", include_superseded=True)
assert sorted((r["path"], r["status"]) for r in a["results"]) == [
    ("practice/durability-rule.md", "superseded"), ("technical/durability-rule.md", "active")], a
put(c4, stub, CANON, "practice/alpha-v1.md", "Alpha plan, v1", "TBD", author="epode", status="superseded")
put(c4, stub, P + "Recto", "practice/zeta-plan.md", "Zeta plan", "TBD")                      # shares a retired body only
assert paths(ask(c4, "zeta plan")) == ["practice/zeta-plan.md"]
assert paths(ask(c4, "zeta plan", scope="mine", seat="Recto")) == ["practice/zeta-plan.md"]
quorum = "Quorum is three seats."
put(c4, stub, CANON, "meta/quorum-v1.md", "The quorum rule, v1", quorum, author="Hesper", status="superseded")
put(c4, stub, P + "Hesper", "meta/quorum-v1.md", "The quorum rule, v1", quorum)
a = ask(c4, "quorum")
assert a["results"] == [] and "include_superseded" in a["note"] and "no entry contains" not in a["note"], a
print("4. an entry canon retired stays out, unflipped copy and all; include_superseded shows it, marked; a moved "
      "entry is found at its live path; an empty answer names what was withheld")


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


class Marked(Embedder):
    """Two directions: an entry that says 'deep' lies along the query; every other entry is across it."""
    semantic, model_id, dim, score_floor = True, "marked-2", 2, 0.5

    def embed(self, texts):
        return [[1.0, 0.0] if "deep" in lexical.words(t) else [0.0, 1.0] for t in texts]

    def embed_query(self, texts):
        return [[1.0, 0.0] for _ in texts]


m_idx, marked = SqliteMapIndex(":memory:"), Marked()
put(m_idx, marked, CANON, "notes/harbor.md", "Harbor", "A plain note.", author="epode")
put(m_idx, marked, CANON, "notes/tide-table.md", "Tide table", "The harbor is deep at the north wall.", author="epode")
a = find_entries(m_idx, marked, "harbor", seat="Repose")           # the name is found by words alone; the other by both legs
assert [(r["path"], r["match"]) for r in a["results"]] == [("notes/harbor.md", "name"), ("notes/tide-table.md", "all-words")], a
assert a["results"][1]["score"] > a["results"][0]["score"] and a["below_floor"] == 1, a   # the order is the ranking, not `score`
for i in range(60):
    put(m_idx, marked, CANON, f"notes/filler-{i:02d}.md", f"Filler {i}", "An unrelated line.", author="epode")
asked, vector_leg = [], m_idx.search
m_idx.search = lambda *args, **kw: (asked.append(kw["limit"]), vector_leg(*args, **kw))[1]
a = find_entries(m_idx, marked, "harbor", seat="Repose")           # the leg is cut, but past a weak hit all are weak
assert len(a["results"]) == 2 and a["below_floor"] == 49 and asked == [50], (a["below_floor"], asked)
print("5. meaning merges by rank: found without a shared word; a name still leads, whatever its score; "
      "the floor is the meaning leg's alone")

# ---- 6. a full answer
full = SqliteMapIndex(":memory:")
seats = [f"s{i:02d}" for i in range(17)]
for term in ("harbor", "harbor wall", "harbor light"):             # three definitions, each echoed by canon and 17 seats
    for holder in ["canon"] + seats:
        put(full, stub, CANON if holder == "canon" else P + holder, f"argot/{term.replace(' ', '-')}.md", term,
            f"{term}: the harbor term every seat carries.", author="Hesper" if holder == "canon" else holder, type="arg")
for i in range(12):
    put(full, stub, CANON, f"technical/port-{i:02d}.md", f"Port study {i}, with a harbor survey",
        f"Study {i} measures the approach.", author="epode")
assert len(ask(full, "harbor", limit=10)["results"]) == 10
assert len(ask(full, "harbor", limit=5)["results"]) == 5
assert len(ask(full, "harbor", limit=50)["results"]) == 15
for i in range(45):                                                 # 45 retired editions, each with an unflipped copy
    body = f"Edition {i} of the ticks rule: ticks, counted in ticks."
    put(full, stub, CANON, f"meta/ticks-v{i:02d}.md", f"The ticks rule, edition {i}", body, author="Hesper", status="superseded")
    put(full, stub, P + "Hesper", f"meta/ticks-v{i:02d}.md", f"The ticks rule, edition {i}", body)
for i in range(5):
    put(full, stub, CANON, f"technical/clock-{i}.md", f"Clock note {i}, on ticks", f"Note {i} about the clock.", author="epode")
a = ask(full, "ticks", limit=3)
assert len(a["results"]) == 3 and all(p.startswith("technical/clock-") for p in paths(a)), a
assert len(ask(full, "ticks", limit=10)["results"]) == 5
print("6. a full answer: echoed copies and retired editions that crowd the candidates do not shorten it")

# ---- 7. the index keeps itself
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
# rows an older-code process writes carry no digest; the next search gives them one, so rules 3 and 4 hold now
put(up, stub, CANON, "meta/quorum-v3.md", "The quorum rule, v3", quorum, author="Hesper")
put(up, stub, P + "Hesper", "meta/quorum-v3.md", "The quorum rule, v3", quorum)
put(up, stub, P + "epode", "meta/log/2a.md", "::2A lands", "The land narrative.", type="log")
legacy = sqlite3.connect(db)
legacy.execute(ins, (CANON, "meta/quorum-v3.md", 1, "Hesper", "kno", "The quorum rule, v3", "superseded", "[]", quorum, "[]"))
legacy.execute(ins, (CANON, "meta/log/2a.md", 1, "epode", "log", "::2A lands", "active", "[]", "The land narrative.", "[]"))
legacy.execute(ins, (P + "Recto", "practice/beans.md", 0, "Recto", "kno", "Roast log", "active", '["caf\\u00e9"]', "Espresso notes.", "[]"))
legacy.commit(); legacy.close()
assert paths(find_entries(up, stub, "quorum", seat="x")) == []                              # canon's flip holds at once
r = find_entries(up, stub, "land narrative", seat="x")["results"]
assert len(r) == 1 and r[0]["is_canon"] and r[0]["holders"] == ["canon", "epode"], r
assert paths(find_entries(up, stub, "", seat="x", tags=["café"])) == ["practice/beans.md"]       # the filter reads older code's spelling
up.conn.close()
again = SqliteMapIndex(db)                                         # the next start levels the table
assert count(again) == (7, 7), count(again)
assert again.conn.execute("SELECT COUNT(*) FROM map_entries WHERE body_hash IS NULL OR body_hash=''").fetchone()[0] == 0
assert paths(find_entries(again, stub, "café", seat="x")) == ["practice/beans.md"]               # and its tag is a name again
again.clear()
assert count(again) == (0, 0)
again.conn.close()
assert body_digest("text ") == body_digest("　text\n") == body_digest("text")           # the guards' own strip
print("7. upkeep: an older index fills on open; a replace leaves no old words; older code still feeds it and its rows "
      "obey both rules at once; clear() empties it")

# ---- 8. two searches at the same moment
for label, target in (("memory", ":memory:"), ("file", os.path.join(work, "race.sqlite"))):
    race = SqliteMapIndex(target)
    for i in range(300):
        put(race, stub, CANON if i % 2 else P + "s00", f"k/word{i}.md", f"word{i} title", f"The body of word{i}. " * 12,
            author="epode" if i % 2 else "s00")
    alone = {i: find_entries(race, stub, f"word{i} title", seat="x") for i in range(300)}
    bad, gate = [], threading.Barrier(2)

    def searcher(offset):
        for n in range(150):
            i = offset + n
            gate.wait()
            try:
                got = find_entries(race, stub, f"word{i} title", seat="x")
            except Exception as err:                                  # noqa: BLE001 — every failure is the finding
                bad.append((i, repr(err)))
                continue
            if got != alone[i]:
                bad.append((i, "another answer"))

    pair = [threading.Thread(target=searcher, args=(o,)) for o in (0, 150)]
    [th.start() for th in pair]
    [th.join() for th in pair]
    assert not bad, (label, len(bad), bad[:3])
    race.conn.close()
print("8. two searches at the same moment, 300 times over: each gets the answer it gets alone")

# ---- 9. without FTS5
idx.fts = False
a = find("legenda")
assert a["mode"] == "approximate" and a["results"] and all(r["match"] == "approximate" for r in a["results"]), a
idx.fts = True
print("9. no FTS5: the embedder alone answers, and the mode says so")


# ---- 10. the wire
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
                                          "title": "Mutually Assured Construction", "tags": ["mac", "στάσιμον"],
                                          "body": "Productive tension between perspectives."})
        got = payload(await c.call_tool("entry_search", {"seat": "Repose", "query": "mutually assured construction"}))
        assert got["mode"] == "words" and got["results"][0]["path"] == "manual/14.md" and got["results"][0]["match"] == "name", got
        got = payload(await c.call_tool("entry_search", {"seat": "Repose", "tags": ["mac"]}))
        assert paths(got) == ["manual/14.md"], got
        got = payload(await c.call_tool("entry_search", {"seat": "Repose", "tags": ["στάσιμον"]}))
        assert paths(got) == ["manual/14.md"], got
        r = await c.call_tool("entry_search", {"seat": "Repose", "query": "  ?! "})
        assert is_err(r) and "`query`" in err_text(r) and "`tags`" in err_text(r), err_text(r)
        r = await c.call_tool("entry_search", {"seat": "Repose", "query": "x", "scope": "everything"})
        assert is_err(r) and "'all', 'canon', or 'mine'" in err_text(r), err_text(r)
    print("10. the wire: tags in the schema, query optional, an empty question and an unknown scope refused with the fix")


anyio.run(wire)
print("\nOK -- entry search: names found, one entry one result, canon decides liveness, legs merge by rank, "
      "answers come back full and whole, the index keeps itself.")
