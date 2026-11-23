# SPDX-License-Identifier: Apache-2.0
"""
Copy with lineage: a write that gives `copy_from` has the server read the body from another canon,
and the copy's envelope records where it came from (`provenance`), nested, for any number of copies.

Three deployments, each a real bare repository: Old (the source), New (copies from Old), Third
(copies from New). Proven here:

  1. config: `copy_sources` parses to {name: path}; each malformed item is refused with the fix;
  2. a copy from canon: the body is the source's body exactly, the title, type and tags come from
     the source when the call leaves them empty, references never do, and `provenance` names the
     copied entry and each earlier edition at the pinned commit;
  3. the chain is found from either side of a pair (one pair in the source is one-sided), and a
     three-edition chain nests three deep;
  4. the true author comes from the source's record, for canon and for a perspective, travels with
     the text through every copy, and stays unknown where the source names none;
  5. every refusal names its fix: a body beside copy_from, an unknown source, this deployment's own
     name, a missing path, a retired entry (the living edition is named), a message, a vantage, a
     seat that is not there, a malformed copy_from, a source that cannot be read;
  6. a proposal copies the same way, the practitioner's preview shows the source, a seat's
     origin_author cannot contradict the source, and the log entry is never a copy;
  7. a land carries the provenance into canon;
  8. a copy of a copy keeps the whole list one level deeper; an entry with both a copy source and
     an earlier edition has two items at one depth;
  9. a retirement keeps the provenance, with the body sent again or with copy_from again; a write
     of another text to the same path is still refused;
 10. a path that holds a comma is quoted, and the list reads back whole.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anyio
from mcp.client import Client as connect
from _testkit import fresh_repo, payload, is_err, err_text
from stasima.cap_server import build_server
from stasima.config import Config, ConfigError
from stasima.local_capstore import LocalCapStore, Identity, Approval, PERSP_PREFIX
from stasima.map_index import SqliteMapIndex, StubEmbedder
from stasima.audit_log import SqliteAuditLog
from stasima.entries import compose_entry, parse_entry
from stasima.canon import land_and_record
from stasima.provenance import read_provenance

CANON = "refs/heads/main"


def e(body, type="kno", title="x", status="active", **extra):
    return compose_entry({"type": type, "title": title, "status": status, **extra}, body).encode()


def deployment(prefix, seed):
    work, gd = fresh_repo(prefix)
    store = LocalCapStore(gd, approvers={"practitioner"})
    store.bootstrap_canon(seed, "bootstrap")
    return work, gd, store, SqliteMapIndex(os.path.join(work, "map.sqlite")), SqliteAuditLog(os.path.join(work, "audit.sqlite"))


def land(store, index, audit, pid):
    prepared = store.prepare_merge("refs/cap/proposals/" + pid)
    return land_and_record(store, index, StubEmbedder(64), audit, prepared,
                           Approval(prepared.candidate_oid, "practitioner", "test"), origin=0)


SKILL_BODY = "The living skill text.\n\nSecond paragraph, with a comma, and [brackets]: kept exactly.\n\n    indented line"

# ---- Old: the source. Canon holds chains; a seat's perspective holds work that never landed.
_, old_gd, old, old_index, old_audit = deployment("cap-copy-old-", {
    "technical/skill.md": e("The first skill text.", title="Skill", status="superseded",
                            superseded_by=["technical/skill-v2.md"]),
    "technical/skill-v2.md": e(SKILL_BODY, title="Skill, second edition: the order of work", tags=["suite", "skill"],
                               supersedes=["technical/skill.md"], references=["technical/clock-v3.md"]),
    # a one-sided pair: the retired edition names its successor; the successor does not name it back
    "technical/orientation/syntax.md": e("Syntax, first.", status="superseded",
                                         superseded_by=["technical/orientation/syntax-v2.md"]),
    "technical/orientation/syntax-v2.md": e("Syntax, living.", type="ori", title="Syntax"),
    "technical/clock.md": e("Clock one.", status="superseded", superseded_by=["technical/clock-v2"]),
    "technical/clock-v2.md": e("Clock two.", status="superseded", supersedes=["technical/clock.md"],
                               superseded_by=["technical/clock-v3.md"]),
    "technical/clock-v3.md": e("Clock three.", title="Clock", supersedes=["technical/clock-v2.md"]),
    "argot/term.md": e("**term** (n.) a word.", type="arg", title="term", tags=["argot"]),
    "practice/alone.md": e("Retired, with no successor.", status="superseded"),
    "practice/a,b.md": e("A path that holds a comma."),
    "meta/log/1.md": e("The first land.", type="log", title="::1", seq="1"),
})
# an entry that reached Old's canon through a proposal by Hesper: the source's record names the author
old.create_branch("refs/cap/proposals/p-old", old.resolve_ref(CANON))
for n, (p, blob) in enumerate({"technical/criterion.md": e("The criterion, by Hesper.", title="The criterion"),
                               "meta/log/2.md": e("Land two.", type="log", title="::2", seq="2")}.items()):
    old.commit("refs/cap/proposals/p-old", {p: blob}, f"KIP {p}", Identity("Hesper"),
               expected_parent=old.resolve_ref("refs/cap/proposals/p-old"), op_id=f"p-old-{n}")
# origin=0 and one bootstrap land already counted: this is Old's ::1 by its own count
old_prepared = old.prepare_merge("refs/cap/proposals/p-old")
try:
    land_and_record(old, old_index, StubEmbedder(64), old_audit, old_prepared,
                    Approval(old_prepared.candidate_oid, "practitioner", "test"), origin=1)
except Exception:
    # the sequence bookkeeping of a hand-built source is not what this test is about: land the merge itself
    old.land_merge(old_prepared, Approval(old_prepared.candidate_oid, "practitioner", "test"))
wren = PERSP_PREFIX + "Wren"
old.commit(wren, {"technical/old.md": e("Wren's first draft.", status="superseded", superseded_by=["technical/draft.md"]),
                  "technical/draft.md": e("Wren's living draft.", title="Wren's draft", supersedes=["technical/old.md"]),
                  "messages/m1.md": e("hello", type="msg"), "vantages/v1-vap.md": e("standpoint", type="vap")},
           "seed", Identity("Wren"), expected_parent=None, op_id="wren-1")
OLD_TIP, WREN_TIP = old.resolve_ref(CANON), old.resolve_ref(wren)
assert "technical/criterion.md" in old.list_paths(CANON)

# ---- New: copies from Old.
new_work, new_gd, new, new_index, new_audit = deployment("cap-copy-new-", {"practice/seed.md": e("seed")})
# ---- Third: copies from New.
third_work, third_gd, third, third_index, third_audit = deployment("cap-copy-third-", {"practice/seed.md": e("seed")})


def new_server():
    return build_server(new, new_index, StubEmbedder(64), new_audit, binding_mode="off", join_gate=False,
                        seq_origin=0, deployment_name="New",
                        copy_sources={"Old": old_gd, "Gone": os.path.join(new_work, "no-such.git")})


def third_server():
    return build_server(third, third_index, StubEmbedder(64), third_audit, binding_mode="off", join_gate=False,
                        seq_origin=0, deployment_name="Third", copy_sources={"New": new_gd})


def held(store, ref, path):
    return parse_entry(store.read_blob(ref, path).decode("utf-8"))


# 1. config
cfgp = os.path.join(new_work, "stasima.toml")


def cfg(lines):
    with open(cfgp, "w", encoding="utf-8") as f:
        f.write(f'git_dir = "{new_gd.replace(os.sep, "/")}"\ndeployment_name = "New"\n' + lines)
    return Config.load(cfgp, env={})


assert cfg("").resolved_copy_sources() == {}
got = cfg(f'copy_sources = ["Old={old_gd.replace(os.sep, "/")}"]').resolved_copy_sources()
assert got == {"Old": old_gd.replace(os.sep, "/")}, got
for bad, word in [('copy_sources = ["Old"]', "Name=path"), ('copy_sources = ["O ld=x.git"]', "letters"),
                  ('copy_sources = ["Old=a.git", "old=b.git"]', "twice"), ('copy_sources = ["New=a.git"]', "own name"),
                  (f'copy_sources = ["Self={new_gd.replace(os.sep, "/")}"]', "own repository"),
                  ('copy_sources = "Old=a.git"', "list")]:
    try:
        cfg(bad)
    except ConfigError as err:
        assert word in str(err), (bad, str(err))
    else:
        raise AssertionError(f"accepted: {bad}")
print("1. config: copy_sources parses; six malformed forms refused, each with the fix")


async def main():
    async with connect(new_server()) as c:
        async def call(tool, **args):
            return await c.call_tool(tool, args)

        # 2. a copy from canon
        r = payload(await call("entry_write", seat="Ada", domain="technical", slug="skill", body="",
                               op_id="a1", copy_from="Old:technical/skill-v2.md"))
        want = [f"1 copy of Old@{OLD_TIP}:technical/skill-v2.md", f"2 supersedes Old@{OLD_TIP}:technical/skill.md"]
        assert r["provenance"] == want and r["copy_of"] == f"Old@{OLD_TIP}:technical/skill-v2.md", r
        ada = PERSP_PREFIX + "Ada"
        env, body = held(new, ada, "technical/skill.md")
        assert body == SKILL_BODY == held(old, CANON, "technical/skill-v2.md")[1], body
        raw = new.read_blob(ada, "technical/skill.md").decode("utf-8")
        assert raw.endswith("---\n\n" + SKILL_BODY + "\n"), raw[-80:]
        assert env["provenance"] == want and env["title"] == "Skill, second edition: the order of work", env
        assert env["tags"] == ["suite", "skill"] and env["type"] == "kno", env
        assert env["references"] == [] and "supersedes" not in env, env        # they name things in Old
        assert read_provenance(env["provenance"]) == [
            {"depth": 1, "relation": "copy of", "address": f"Old@{OLD_TIP}:technical/skill-v2.md"},
            {"depth": 2, "relation": "supersedes", "address": f"Old@{OLD_TIP}:technical/skill.md"}]
        # what the call gives, the call keeps
        r = payload(await call("entry_write", seat="Ada", domain="argot", slug="term", body="", op_id="a2",
                               copy_from="Old:argot/term", title="term, as New holds it", tags=["kept"]))
        env, _ = held(new, ada, "argot/term.md")
        assert env["title"] == "term, as New holds it" and env["tags"] == ["kept"] and env["type"] == "arg", env
        assert env["provenance"] == [f"1 copy of Old@{OLD_TIP}:argot/term.md"], env
        assert "origin_author" not in env, env     # a bootstrap commit names no seat: unknown stays unknown
        st = payload(await call("canon_state"))
        assert st["copy_sources"] == ["Gone", "Old"], st
        print("2. copy from canon: body exact, envelope defaults from the source, provenance pinned")

        # 3. chains: the one-sided pair, and three editions
        r = payload(await call("entry_write", seat="Ada", domain="technical/orientation", slug="syntax", body="",
                               op_id="a3", copy_from="Old:technical/orientation/syntax-v2.md"))
        assert r["provenance"] == [f"1 copy of Old@{OLD_TIP}:technical/orientation/syntax-v2.md",
                                   f"2 supersedes Old@{OLD_TIP}:technical/orientation/syntax.md"], r
        assert held(new, ada, "technical/orientation/syntax.md")[0]["type"] == "ori"
        r = payload(await call("entry_write", seat="Ada", domain="technical", slug="clock", body="", op_id="a4",
                               copy_from="Old:technical/clock-v3.md"))
        assert r["provenance"] == [f"1 copy of Old@{OLD_TIP}:technical/clock-v3.md",
                                   f"2 supersedes Old@{OLD_TIP}:technical/clock-v2.md",
                                   f"3 supersedes Old@{OLD_TIP}:technical/clock.md"], r
        print("3. chains: found from either side of a pair; three editions nest three deep")

        # 4. the true author
        r = payload(await call("entry_write", seat="Ada", domain="technical", slug="criterion", body="", op_id="a5",
                               copy_from="Old:technical/criterion.md"))
        assert held(new, ada, "technical/criterion.md")[0]["origin_author"] == "Hesper"
        r = payload(await call("entry_write", seat="Ada", domain="technical", slug="draft", body="", op_id="a6",
                               copy_from="Old/Wren:technical/draft.md"))
        env, body = held(new, ada, "technical/draft.md")
        assert env["origin_author"] == "Wren" and body == "Wren's living draft.", env
        assert env["provenance"] == [f"1 copy of Old/Wren@{WREN_TIP}:technical/draft.md",
                                     f"2 supersedes Old/Wren@{WREN_TIP}:technical/old.md"], env
        print("4. the true author: from the source's history for canon, the seat for a perspective")

        # 5. refusals, each with its fix
        async def refused(words, **args):
            base = dict(seat="Ada", domain="practice", slug="r", body="", op_id="r")
            res = await call("entry_write", **{**base, **args})
            assert is_err(res), (args, payload(res))
            for w in words:
                assert w in err_text(res), (w, err_text(res))
        await refused(["not both", "body=''"], copy_from="Old:argot/term.md", body="my own text")
        await refused(["'Nowhere'", "Gone, Old"], copy_from="Nowhere:argot/term.md")
        await refused(["this deployment", "origin_author"], copy_from="New:practice/seed.md")
        await refused(["holds no entry at technical/none.md"], copy_from="Old:technical/none.md")
        await refused(["retired at the source", "Old:technical/skill-v2.md", "copy that one"],
                      copy_from="Old:technical/skill.md")
        await refused(["retired at the source", "Old:technical/clock-v3.md"], copy_from="Old:technical/clock.md")
        await refused(["retired at the source", "no living edition"], copy_from="Old:practice/alone.md")
        await refused(["a message", "stays where"], copy_from="Old/Wren:messages/m1.md")
        await refused(["a vantage"], copy_from="Old/Wren:vantages/v1-vap.md")
        await refused(["no perspective named 'wren'", "it has 'Wren'", "exact"], copy_from="Old/wren:technical/draft.md")
        await refused(["no perspective named 'Nobody'"], copy_from="Old/Nobody:technical/draft.md")
        await refused(["'<Source>:<path>'"], copy_from="technical/skill-v2.md")
        await refused(["'<Source>:<path>'", "pins the commit"], copy_from=f"Old@{OLD_TIP}:technical/skill-v2.md")
        await refused(["Gone", "copy_sources"], copy_from="Gone:technical/skill-v2.md")
        assert "practice/r.md" not in new.list_paths(ada)
        denied = [x for x in new_audit.events(op="entry_write") if x.get("outcome") == "denied"]
        assert any((x.get("detail") or {}).get("reason") == "copy_from refused" for x in denied), denied[-2:]
        print("5. refusals: fourteen, each naming its fix; nothing written; each on the audit log")

        # 6. a proposal copies the same way
        payload(await call("canon_diff", seat="Ada"))
        payload(await call("canon_reconcile", seat="Ada", body="first pull; nothing to revise"))
        r = payload(await call("proposal_append_entry", seat="Ada", proposal_id="p1", domain="technical", slug="skill",
                               body="", op_id="p1-a", copy_from="Old:technical/skill-v2.md"))
        assert r["provenance"] == want, r
        r = payload(await call("proposal_append_entry", seat="Ada", proposal_id="p1", domain="technical",
                               slug="criterion", body="", op_id="p1-b", copy_from="Old:technical/criterion.md"))
        res = await call("proposal_append_entry", seat="Ada", proposal_id="p1", domain="technical", slug="crit2",
                         body="", op_id="p1-c", copy_from="Old:technical/criterion.md", origin_author="Ada")
        assert is_err(res) and "written by 'Hesper'" in err_text(res), err_text(res)
        res = await call("proposal_append_entry", seat="Ada", proposal_id="p1", domain="meta/log", slug="1", seq="1",
                         type="log", body="", op_id="p1-d", copy_from="Old:meta/log/1.md")
        assert is_err(res) and "account of THIS land" in err_text(res), err_text(res)
        payload(await call("proposal_append_entry", seat="Ada", proposal_id="p1", domain="meta/log", slug="1", seq="1",
                           type="log", title="::1", body="Two entries copied from Old.", op_id="p1-e"))
        pv = payload(await call("proposal_preview", proposal_id="p1"))
        assert pv["attributions"]["technical/criterion.md"] == {
            "authored": "Hesper", "proposed": "Ada", "copy_of": f"Old@{OLD_TIP}:technical/criterion.md"}, pv
        assert pv["attributions"]["technical/skill.md"]["copy_of"] == f"Old@{OLD_TIP}:technical/skill-v2.md", pv
        print("6. proposal: copies the same way; the preview shows each source; the log entry is never a copy")

        # 7. the land carries it into canon
        out = land(new, new_index, new_audit, "p1")
        assert out["landed"] and not out.get("warnings"), out
        env, body = held(new, CANON, "technical/skill.md")
        assert env["provenance"] == want and body == SKILL_BODY, env
        hits = payload(await call("entry_search", seat="Ada", query="living skill text", scope="canon"))
        assert "technical/skill.md" in str(hits), hits
        print("7. land: canon holds the copy with its provenance; search finds it")

        # 9. a retirement keeps the provenance
        payload(await call("entry_write", seat="Ada", domain="technical", slug="skill-next", op_id="a7",
                           body="Ada's new edition, written in New.", supersedes=["technical/skill.md"]))
        payload(await call("entry_write", seat="Ada", domain="technical", slug="skill", op_id="a8", body=SKILL_BODY,
                           status="superseded", superseded_by=["technical/skill-next.md"],
                           title="Skill, second edition: the order of work"))
        env, body = held(new, ada, "technical/skill.md")
        assert env["status"] == "superseded" and env["provenance"] == want, env
        payload(await call("entry_write", seat="Ada", domain="technical", slug="criterion", op_id="a8b",
                           body="The criterion, by Hesper.", status="superseded",
                           superseded_by=["technical/criterion-next.md"]))
        env, _ = held(new, ada, "technical/criterion.md")
        assert env["origin_author"] == "Hesper" and env["provenance"][0].startswith("1 copy of Old@"), env
        payload(await call("entry_write", seat="Ada", domain="technical", slug="clock", op_id="a9", body="",
                           copy_from="Old:technical/clock-v3.md", status="superseded",
                           superseded_by=["technical/clock-next.md"]))
        env, _ = held(new, ada, "technical/clock.md")
        assert env["status"] == "superseded" and len(env["provenance"]) == 3, env
        res = await call("entry_write", seat="Ada", domain="technical", slug="clock", op_id="a10", body="",
                         copy_from="Old:argot/term.md")
        assert is_err(res) and "body never changes" in err_text(res), err_text(res)
        # an entry with both a copy source and an earlier edition of its own
        payload(await call("entry_write", seat="Ada", domain="technical", slug="b", op_id="a11", body="Ada's own b."))
        payload(await call("entry_write", seat="Ada", domain="technical", slug="b-v2", op_id="a12", body="",
                           copy_from="Old:argot/term.md", supersedes=["technical/b.md"]))
        r = payload(await call("entry_write", seat="Ada", domain="practice", slug="a-b", op_id="a13", body="",
                               copy_from="Old:practice/a,b.md"))
        assert r["provenance"] == [f"1 copy of Old@{OLD_TIP}:practice/a%2Cb.md"], r
        assert held(new, ada, "practice/a-b.md")[0]["provenance"] == r["provenance"]
        print("9. retirement keeps the provenance (body sent, or copy_from again); another text is refused")
        print("10. a comma in a source path is quoted; the list reads back whole")

    NEW_TIP, ADA_TIP = new.resolve_ref(CANON), new.resolve_ref(PERSP_PREFIX + "Ada")
    async with connect(third_server()) as c:
        async def call(tool, **args):
            return await c.call_tool(tool, args)
        # 8. a copy of a copy
        r = payload(await call("entry_write", seat="Bea", domain="technical", slug="skill", body="", op_id="b1",
                               copy_from="New:technical/skill.md"))
        assert r["provenance"] == [f"1 copy of New@{NEW_TIP}:technical/skill.md",
                                   f"2 copy of Old@{OLD_TIP}:technical/skill-v2.md",
                                   f"3 supersedes Old@{OLD_TIP}:technical/skill.md"], r
        env, body = held(third, PERSP_PREFIX + "Bea", "technical/skill.md")
        assert body == SKILL_BODY and env["provenance"] == r["provenance"], env
        # Ada's new edition superseded her copy: the earlier edition's own sourcing rides under it
        r = payload(await call("entry_write", seat="Bea", domain="technical", slug="skill-next", body="", op_id="b2",
                               copy_from="New/Ada:technical/skill-next.md"))
        assert r["provenance"] == [f"1 copy of New/Ada@{ADA_TIP}:technical/skill-next.md",
                                   f"2 supersedes New/Ada@{ADA_TIP}:technical/skill.md",
                                   f"3 copy of Old@{OLD_TIP}:technical/skill-v2.md",
                                   f"4 supersedes Old@{OLD_TIP}:technical/skill.md"], r
        # a copy source and an earlier edition under one entry: two items at depth 2
        r = payload(await call("entry_write", seat="Bea", domain="technical", slug="b", body="", op_id="b3",
                               copy_from="New/Ada:technical/b-v2.md"))
        assert r["provenance"] == [f"1 copy of New/Ada@{ADA_TIP}:technical/b-v2.md",
                                   f"2 copy of Old@{OLD_TIP}:argot/term.md",
                                   f"2 supersedes New/Ada@{ADA_TIP}:technical/b.md"], r
        assert [x["depth"] for x in read_provenance(r["provenance"])] == [1, 2, 2]
        # the text is Old's, with no author on record there: Ada, who copied it, is not named as its author
        assert "origin_author" not in held(third, PERSP_PREFIX + "Bea", "technical/b.md")[0]
        r = payload(await call("entry_write", seat="Bea", domain="technical", slug="criterion", body="", op_id="b4",
                               copy_from="New:technical/criterion.md"))
        assert held(third, PERSP_PREFIX + "Bea", "technical/criterion.md")[0]["origin_author"] == "Hesper"
        print("8. a copy of a copy: the whole list one level deeper; two parents sit at one depth")

    # the sources were only read
    assert old.resolve_ref(CANON) == OLD_TIP and old.resolve_ref(wren) == WREN_TIP
    assert new.resolve_ref(CANON) == NEW_TIP
    print("the sources are unchanged")


anyio.run(main)
print("\ncopy with lineage: ALL PASS")
