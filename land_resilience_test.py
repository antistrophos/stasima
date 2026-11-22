# SPDX-License-Identifier: Apache-2.0
"""
A land that has moved canon is never reported as failed, and one entry never costs the index the rest.

Four defects in 0.3.0, each reproduced here against a real bare repository:
  1. An envelope value that begins "[" and ends "]" was read back as a list, for any field. A title
     or a subject of that shape was accepted at the write; the land's index step then raised after
     canon had moved, and every later rebuild stopped at that entry with the index already cleared.
  2. The store's reader of changed paths split git's output on whitespace, so a path that holds a
     space became two paths that do not exist, and the land's index step raised the same way.
  3. The land routine had no handler after the merge: a failure in a later step left canon moved,
     no audit anchor, and the caller told the land had failed.
  4. (in audit_test.py and map_index_test.py) two reads at the same moment could exchange rows.
"""
import os
import subprocess as sp
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stasima.local_capstore import LocalCapStore, Identity, Approval
from stasima.map_index import SqliteMapIndex, StubEmbedder
from stasima.audit_log import SqliteAuditLog
from stasima.entries import compose_entry, parse_entry, LIST_KEYS
from stasima.canon import land_and_record, reindex_from_git

CANON = "refs/heads/main"
def persp(i): return f"refs/cap/perspectives/{i}"
def prop(p): return f"refs/cap/proposals/{p}"


def fresh(tag):
    gd = os.path.join(tempfile.mkdtemp(prefix=f"cap-land-{tag}-"), "stasima.git")
    sp.run(["git", "init", "--bare", "-q", gd], check=True)
    store = LocalCapStore(gd, approvers={"practitioner"})
    store.bootstrap_canon({"practice/first.md": compose_entry(
        {"type": "kno", "title": "First", "status": "active"}, "The first entry.").encode()}, "Bootstrap canon")
    return store, SqliteMapIndex(":memory:"), StubEmbedder(dim=64), SqliteAuditLog(":memory:")


def author(store, ref, path, envelope, body, who, op_id):
    return store.commit(ref, {path: compose_entry(envelope, body).encode()}, f"KIP {path}",
                        Identity(who), expected_parent=store.resolve_ref(ref), op_id=op_id)


def propose(store, pid, entries, seq, who="alice"):
    store.create_branch(prop(pid), store.resolve_ref(CANON))
    for n, (path, envelope, body) in enumerate(entries):
        author(store, prop(pid), path, envelope, body, who, f"{pid}-{n}")
    author(store, prop(pid), f"meta/log/{seq}.md",
           {"type": "log", "title": f"land {seq}", "status": "active", "seq": seq}, "A land.", who, f"{pid}-log")


def land(store, index, emb, audit, pid):
    prepared = store.prepare_merge(prop(pid))
    return land_and_record(store, index, emb, audit, prepared,
                           Approval(prepared.candidate_oid, "practitioner", "test"), origin=0)


def rows(index):
    return {r["path"]: r for r in index.conn.execute("SELECT * FROM map_entries WHERE is_canon=1")}


# ============================================================ 1. the parser: only a list field is a list
print("== a bracketed value is a list only in a list field ==")
for value in ("[draft] A rule [v2]", "[urgent]", "[]", "[a, b]"):
    for field in ("title", "subject", "status", "thread", "origin_author", "seq"):
        env, body = parse_entry(compose_entry({"type": "kno", field: value}, "b"))
        assert env[field] == value and body == "b", (field, value, env)
env, _ = parse_entry(compose_entry({k: ["a", "b"] for k in sorted(LIST_KEYS)}, "b"))
assert all(env[k] == ["a", "b"] for k in LIST_KEYS), env
env, _ = parse_entry(compose_entry({k: [] for k in sorted(LIST_KEYS)}, "b"))
assert all(env[k] == [] for k in LIST_KEYS), env
# every list field the server writes today is in LIST_KEYS: an envelope as each writer builds it
written = {"type": "msg", "title": "t", "status": "active", "tags": ["x"], "references": ["a/b.md"],
           "supersedes": ["a/c.md"], "superseded_by": ["a/d.md"], "recipients": ["r"], "coordinates": ["a/e.md"]}
assert parse_entry(compose_entry(written, "b"))[0] == written
print("   title, subject, status, thread, origin_author, seq keep a bracketed value as text      OK")

# ============================================================ 2. a bracketed title lands, and is indexed
print("== a title that begins '[' and ends ']' ==")
store, index, emb, audit = fresh("title")
propose(store, "p1", [("practice/bracket.md", {"type": "kno", "title": "[draft] A rule [v2]", "status": "active"},
                       "A body about brackets.")], "1")
out = land(store, index, emb, audit, "p1")
assert "warnings" not in out, out
assert store.resolve_ref("refs/tags/state/1") == out["landed"] and out["anchor"]["head"]
assert rows(index)["practice/bracket.md"]["title"] == "[draft] A rule [v2]"
assert reindex_from_git(store, index, emb) == 3 and rows(index)["practice/bracket.md"]["title"] == "[draft] A rule [v2]"
print("   lands, anchors, indexes with its title, and a rebuild keeps it                       OK")

# ============================================================ 3. a bracketed subject survives a rebuild
print("== a subject that begins '[' and ends ']' ==")
store, index, emb, audit = fresh("subject")
for who, op, subject in (("alice", "m1", "an ordinary message"), ("zed", "m2", "[urgent]"), ("zoe", "m3", "a later one")):
    author(store, persp(who), f"messages/{op}.md",
           {"type": "msg", "subject": subject, "status": "active", "recipients": ["bob"], "coordinates": []},
           "hello", who, op)
failed = []
assert reindex_from_git(store, index, emb, failed=failed) == 4 and failed == [], failed
assert sorted(m.subject for m in index.inbox("bob")) == ["[urgent]", "a later one", "an ordinary message"]
print("   three messages sent, three in the inbox after a rebuild                               OK")

# ============================================================ 4. a path that holds a space
print("== a path that holds a space, and one outside ASCII ==")
store, index, emb, audit = fresh("space")
propose(store, "p2", [("technical/two words.md", {"type": "kno", "title": "Two words", "status": "active"}, "A body."),
                      ("technical/café.md", {"type": "kno", "title": "Café", "status": "active"}, "A body.")], "1")
out = land(store, index, emb, audit, "p2")
assert "warnings" not in out, out
landed = store.changed_paths(f"{out['landed']}^1", out["landed"])
assert sorted(landed) == ["meta/log/1.md", "technical/café.md", "technical/two words.md"], landed
assert {"technical/two words.md", "technical/café.md"} <= set(rows(index)), sorted(rows(index))
print("   both land whole and are indexed under their own names                                 OK")

# ============================================================ 5. after the merge, nothing fails the land
print("== a step that fails after the merge ==")


class Choosy(StubEmbedder):
    """Refuses one entry — any failure of the index step, for any reason."""
    def embed(self, texts):
        if any("POISON" in t for t in texts):
            raise RuntimeError("the embedder is down")
        return super().embed(texts)


store, index, emb, audit = fresh("after")
emb = Choosy(dim=64)
propose(store, "p3", [("practice/good.md", {"type": "kno", "title": "Good", "status": "active"}, "A good body."),
                      ("practice/bad.md", {"type": "kno", "title": "Bad", "status": "active"}, "POISON body.")], "1")
before = store.resolve_ref(CANON)
out = land(store, index, emb, audit, "p3")
assert store.resolve_ref(CANON) == out["landed"] != before, "canon moved, and the caller is told so"
assert store.resolve_ref("refs/tags/state/1") == out["landed"], "the state tag is set"
assert out["anchor"] and out["anchor"]["head"], "the audit anchor is written though the index step failed"
assert [(w["step"], w.get("path")) for w in out["warnings"]] == [("index", "practice/bad.md")], out["warnings"]
assert "RuntimeError" in out["warnings"][0]["error"]
assert "practice/good.md" in rows(index) and "meta/log/1.md" in rows(index) and "practice/bad.md" not in rows(index)
assert audit.latest(op="land_merge")["result_oid"] == out["landed"]
print("   landed, tagged, anchored; the entry that failed is named; the others are indexed       OK")

# the next land is not held up by the last one's warning
propose(store, "p4", [("practice/next.md", {"type": "kno", "title": "Next", "status": "active"}, "The next body.")], "2")
out2 = land(store, index, emb, audit, "p4")
assert "warnings" not in out2 and out2["seq"] == "2", out2
print("   the next land runs clean at the next seq                                                OK")

# a rebuild sets the same entry aside, names it, and indexes every entry after it
failed = []
n = reindex_from_git(store, index, emb, failed=failed)
assert [(f["ref"], f["path"]) for f in failed] == [(CANON, "practice/bad.md")], failed
assert n == len(rows(index)) == 5 and "practice/next.md" in rows(index), (n, sorted(rows(index)))
print("   a rebuild sets it aside, names it, and indexes the rest                                OK")

# a step that fails whole (not one entry of it) is named too, and the steps after it still run
store, index, emb, audit = fresh("whole")
propose(store, "p5", [("practice/x.md", {"type": "kno", "title": "X", "status": "active"}, "An x body.")], "1")
real_tag = store.tag


def no_tag(name, at):
    raise OSError("the disk refused the tag")


store.tag = no_tag
out = land(store, index, emb, audit, "p5")
store.tag = real_tag
assert [w["step"] for w in out["warnings"]] == ["tag"] and store.resolve_ref(CANON) == out["landed"]
assert "practice/x.md" in rows(index) and out["anchor"]["head"], "index and anchor ran after the failed step"
print("   a failed step is named and the later steps still run                                   OK")

# what may still refuse a land is everything BEFORE the merge: a bad log entry leaves canon where it was
store, index, emb, audit = fresh("refuse")
store.create_branch(prop("p6"), store.resolve_ref(CANON))
author(store, prop("p6"), "practice/y.md", {"type": "kno", "title": "Y", "status": "active"}, "A y body.", "alice", "p6-0")
before = store.resolve_ref(CANON)
try:
    land(store, index, emb, audit, "p6")
    raise AssertionError("a proposal with no log entry must not land")
except ValueError:
    pass
assert store.resolve_ref(CANON) == before
print("   a refusal before the merge still refuses, and canon does not move                      OK")

print("\nOK -- bracketed values, spaced paths, and steps after the merge all verified.")
