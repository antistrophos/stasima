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
           {"type": "log", "title": f"land {seq}", "status": "active", "seq": seq}, f"A land, proposed as {pid}.",
           who, f"{pid}-log")


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
# the six list fields the writers build today (written out by hand here: a writer that gains a
# list field must add it to LIST_KEYS, and this literal does not watch the writers for that)
written = {"type": "msg", "title": "t", "status": "active", "tags": ["x"], "references": ["a/b.md"],
           "supersedes": ["a/c.md"], "superseded_by": ["a/d.md"], "recipients": ["r"], "coordinates": ["a/e.md"]}
assert parse_entry(compose_entry(written, "b"))[0] == written
print("   title, subject, status, thread, origin_author, seq keep a bracketed value as text      OK")

# the front matter closes at a LINE that is ---, never at --- inside a value
for value in ("Before --- after", "a---b", "---", "--- leading", "trailing ---"):
    src = {"type": "kno", "title": value, "status": "superseded", "tags": ["t"], "superseded_by": ["a/n.md"]}
    env, body = parse_entry(compose_entry(src, "A body.\n\n---\n\nA rule after a horizontal line."))
    assert env == src and body == "A body.\n\n---\n\nA rule after a horizontal line.", (value, env, body)
assert parse_entry("no front matter") == ({}, "no front matter")
assert parse_entry("---\ntitle: never closed\n") == ({}, "---\ntitle: never closed\n")
print("   a value that holds --- keeps the whole envelope, and a --- line in the body is body     OK")

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
# a rebuild lists the same paths as git holds them (git quotes a path outside ASCII unless asked not to)
assert "technical/café.md" in store.list_paths(CANON), store.list_paths(CANON)
assert sorted(e.name for e in store.list_tree(CANON, "technical")) == ["café.md", "two words.md"]
failed = []
assert reindex_from_git(store, index, emb, failed=failed) == 4 and failed == [], failed
assert {"technical/two words.md", "technical/café.md"} <= set(rows(index)), sorted(rows(index))
print("   both land whole, are indexed under their own names, and survive a rebuild            OK")

# a name that holds a newline never rides the blob sidecar (one request per line): reads after it stay true
author(store, persp("alice"), "practice/one.md", {"type": "kno", "title": "One", "status": "active"}, "BODY ONE", "alice", "o1")
author(store, persp("alice"), "practice/two.md", {"type": "kno", "title": "Two", "status": "active"}, "BODY TWO", "alice", "o2")
try:
    store.read_blob(persp("alice"), "practice/bad\nslug.md")
    raise AssertionError("no such path")
except Exception as err:                                  # noqa: BLE001
    assert type(err).__name__ == "PathNotFound", repr(err)
for n in range(3):
    assert b"BODY ONE" in store.read_blob(persp("alice"), "practice/one.md")
    assert b"BODY TWO" in store.read_blob(persp("alice"), "practice/two.md")
print("   a read of a name with a newline misses, and the reads after it return their own bodies  OK")

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
repair = out["warnings"][0]["repair"]
assert repair.endswith(f"tag state/1 {out['landed']}") and store.git_dir in repair, repair
print("   a failed step is named and the later steps still run                                   OK")

# the tag is missing, so canon's seq did not advance. The next land at the same seq is REFUSED:
# it would rewrite the log entry of the land that happened. Set the tag, renumber, and it lands.
propose(store, "p5b", [("practice/z.md", {"type": "kno", "title": "Z", "status": "active"}, "A z body.")], "1")
first_story = store.read_blob(CANON, "meta/log/1.md")
try:
    land(store, index, emb, audit, "p5b")
    raise AssertionError("a second land at the same seq must not rewrite the first land's log entry")
except ValueError as err:
    assert "already holds meta/log/1.md" in str(err), err
assert store.read_blob(CANON, "meta/log/1.md") == first_story and store.resolve_ref(CANON) == out["landed"]
store.tag("state/1", out["landed"])                     # the repair, as the warning gave it
propose(store, "p5c", [("practice/z.md", {"type": "kno", "title": "Z", "status": "active"}, "A z body.")], "2")
out3 = land(store, index, emb, audit, "p5c")
assert "warnings" not in out3 and out3["seq"] == "2" and store.read_blob(CANON, "meta/log/1.md") == first_story
print("   with the tag missing the next land is refused; with the tag set it lands at the next seq OK")

# the audit row is tried again before it is given up; one that never writes is a named warning
store, index, emb, audit = fresh("auditrow")
propose(store, "p7", [("practice/a.md", {"type": "kno", "title": "A", "status": "active"}, "An a body.")], "1")
real_append, calls = audit.append, []


def flaky(actor, op, **kw):
    if op == "land_merge":
        calls.append(op)
        if len(calls) < 3:
            raise RuntimeError("the audit file is busy")
    return real_append(actor, op, **kw)


audit.append = flaky
out = land(store, index, emb, audit, "p7")
assert "warnings" not in out and len(calls) == 3 and audit.latest(op="land_merge")["result_oid"] == out["landed"]
propose(store, "p8", [("practice/b.md", {"type": "kno", "title": "B", "status": "active"}, "A b body.")], "2")


def never(actor, op, **kw):
    if op == "land_merge":
        raise RuntimeError("the audit file is gone")
    return real_append(actor, op, **kw)


audit.append = never
out = land(store, index, emb, audit, "p8")
audit.append = real_append
assert [w["step"] for w in out["warnings"]] == ["audit"] and store.resolve_ref("refs/tags/state/2") == out["landed"]
assert "practice/b.md" in rows(index) and out["anchor"]["head"]
print("   the audit row is tried three times; if it never writes, the land stands and says so     OK")

# a failed anchor, a failed diff in the index step, a failure while describing the merge, and a
# closed stderr: each leaves a land that returns, with canon moved and the failure named
store, index, emb, audit = fresh("holes")
propose(store, "p9", [("practice/c.md", {"type": "kno", "title": "C", "status": "active"}, "A c body.")], "1")
real_diff, real_describe, real_stderr = store.changed_paths, store._commit_result, sys.stderr


def strict_fails(a, b, strict=False):
    if strict:
        raise RuntimeError("git could not make the diff")
    return real_diff(a, b)


described = []


def no_describe(oid, ref, replayed=False):
    described.append(oid)
    if len(described) == 1:                              # the land's own; later commits describe normally
        raise RuntimeError("git timed out after the ref moved")
    return real_describe(oid, ref, replayed)


store.changed_paths, store._commit_result = strict_fails, no_describe
sys.stderr = open(os.devnull, "w")
sys.stderr.close()                                       # every write to it now raises ValueError
try:
    out = land(store, index, emb, audit, "p9")
finally:
    sys.stderr = real_stderr
    store.changed_paths, store._commit_result = real_diff, real_describe
assert store.resolve_ref(CANON) == out["landed"] and store.resolve_ref("refs/tags/state/1") == out["landed"]
assert [w["step"] for w in out["warnings"]] == ["index"] and out["anchor"]["head"], out
print("   a failed diff, a failed describe and a closed stderr: the land returns and names the step OK")

# an embedder that is down stops a rebuild BEFORE the index is cleared
class Down(StubEmbedder):
    def embed(self, texts):
        raise RuntimeError("the embedder is down")


assert reindex_from_git(store, index, emb) == 3
before_rows = sorted(rows(index))
try:
    reindex_from_git(store, index, Down(dim=64))
    raise AssertionError("a rebuild with no embedder must raise")
except RuntimeError:
    pass
assert sorted(rows(index)) == before_rows and before_rows, "the index is as it was"
print("   with the embedder down a rebuild raises and leaves the index as it was                  OK")

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
