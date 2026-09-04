# SPDX-License-Identifier: Apache-2.0
"""
The stacks, driven with NO transport in the process: the back end's two doors and its read shelf,
called directly. This is the proof that the desk-and-stacks split is a real layer boundary — the
store law runs behind the door whoever knocks, and a front end that is not MCP (a carrier's sync,
a signed envelope off a radio) reaches the same law through the same calls.

  door 1  apply(principal, op)                 — an authored act under a name the front end resolved
  shelf   call(name, **args)                   — reads, unguarded by design
  door 2  advance_replica(carrier, ref, new, expected_old) — a structural fast-forward, no authoring
"""
import os
import subprocess as sp
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from stasima.local_capstore import LocalCapStore, NonFastForward, StaleRef, CapStoreError
from stasima.map_index import SqliteMapIndex, StubEmbedder
from stasima.audit_log import SqliteAuditLog
from stasima.authz import Denied, DefaultPolicy
from stasima.entries import parse_entry
from stasima.stacks import build_stacks, Principal, Op

work = tempfile.mkdtemp(prefix="stacks-")
gd = os.path.join(work, "stasima.git")
sp.run(["git", "init", "--bare", "-q", gd], check=True)
store = LocalCapStore(gd, approvers={"practitioner"})
index, emb, audit = SqliteMapIndex(":memory:"), StubEmbedder(dim=64), SqliteAuditLog(":memory:")
S = build_stacks(store, index, emb, audit, DefaultPolicy())

# an EMPTY deployment first: the reconcile hinge must refuse cleanly, not fall over on a missing tip
try:
    S.apply(Principal(name="Verso"), Op("sup_reconcile", {"body": "read"}))
    raise SystemExit("FAIL: reconcile against no canon passed")
except Denied as e:
    assert "no canon exists yet" in str(e), e
from stasima.entries import compose_entry
seed = {"technical/orientation/welcome.md": compose_entry(
    {"type": "ori", "title": "Welcome", "status": "active"}, "Welcome.").encode()}
for n in (1, 2, 10, 16, 0x1a):   # git lists these lexically: 1, 10, 16, 1a, 2 — the seat must see sequence
    seed[f"meta/log/{n:x}.md"] = compose_entry({"type": "log", "title": f"::{n:X}", "status": "active"},
                                                f"land {n:x}").encode()
store.bootstrap_canon(seed, "bootstrap")
print("empty deployment    OK (reconcile with no canon refuses with the instruction)")

# the pull orders log entries by SEQUENCE, not by git's lexical path order (Alidade's finding)
cd = S.apply(Principal(name="Scout"), Op("canon_diff", {}))   # a seat that only reads; Verso stays un-pulled below
assert [l["path"] for l in cd["logs"]] == [f"meta/log/{n:x}.md" for n in (1, 2, 10, 16, 0x1a)], cd["logs"]
assert cd["changed"][0]["path"] == "meta/log/1.md" and cd["changed"][-1]["path"].startswith("technical/"), cd["changed"]
print("pull order          OK (logs lead in hex-sequence order; the rest follow in path order)")

# ---- the registry is the surface: the wire's 29 minus whoami (the desk's own) minus the three
# relay verbs (no airlock in this assembly) = 25; writes identified by their signature ----
assert len(S.ops) == 25, sorted(S.ops)
assert {"kip_commit", "propose", "imp_send", "vap_record", "sup_reconcile", "canon_diff",
        "imp_mark_read", "propose_retract", "propose_close", "announce"} <= S.writes, S.writes
assert "kip_get" not in S.writes and "whoami" not in S.ops   # whoami is the desk's: it reports binding
print(f"registry            OK ({len(S.ops)} ops, {len(S.writes)} writes; whoami stays at the desk)")

# ---- door 1: an authored op, no MCP anywhere ----
verso = Principal(name="Verso", source="pinned", session="s0000test")
r = S.apply(verso, Op("kip_commit", {"domain": "state", "slug": "one", "body": "first", "op_id": "k1"}, "k1"))
assert r["author"] == "Verso" and r["path"] == "state/one.md", r
got = S.call("kip_get", ref="Verso", path="state/one.md")
env, body = parse_entry(got["text"])
assert body.strip() == "first" and "authored_via" not in env, (env, body)
rows = [e for e in audit.events(op="kip_commit") if e["actor"] == "Verso"]
assert rows and rows[-1]["detail"].get("session") == "s0000test", rows[-1]   # the label rides the row
print("door 1 apply        OK (kip_commit through the door; read back off the shelf; session label on the audit row)")

# the witness stamp is the FRONT END's decision — the stacks record what they were handed
recto_as_verso = Principal(name="Recto", stamp={"authored_via": "Verso"}, source="process")
r2 = S.apply(recto_as_verso, Op("kip_commit", {"domain": "state", "slug": "wit", "body": "w", "op_id": "k2"}, "k2"))
env2, _ = parse_entry(S.call("kip_get", ref="Recto", path="state/wit.md")["text"])
assert env2.get("authored_via") == "Verso", env2
print("witness stamp       OK (the desk's stamp lands in the envelope; the stacks judge nothing about WHO)")

# store law runs BEHIND the door: immutability, the reconcile hinge, attribution
try:
    S.apply(verso, Op("kip_commit", {"domain": "state", "slug": "one", "body": "changed", "op_id": "k3"}, "k3"))
    raise SystemExit("FAIL: an immutable body was rewritten through the door")
except Denied as e:
    assert "immutable" in str(e), e
try:
    S.apply(verso, Op("sup_reconcile", {"body": "read"}))
    raise SystemExit("FAIL: reconcile without a pull passed the hinge")
except Denied as e:
    assert "canon_diff" in str(e), e
print("store law           OK (immutability + the reconcile hinge refuse behind the door, not at the desk)")

# the doors are typed: a read cannot come through apply, a write cannot come off the shelf
for bad in (lambda: S.apply(verso, Op("kip_get", {"ref": "Verso", "path": "state/one.md"})),
            lambda: S.call("kip_commit", domain="state", slug="x", body="x", op_id="x"),
            lambda: S.call("no_such_op")):
    try:
        bad()
        raise SystemExit("FAIL: a mis-typed door call passed")
    except Denied:
        pass
print("typed doors         OK (reads off the shelf, writes through the door, unknown ops refused)")

# ---- door 2: a carrier advances a replica ref by fast-forward only ----
t1 = store.resolve_ref("refs/cap/perspectives/Verso")
S.apply(verso, Op("kip_commit", {"domain": "state", "slug": "two", "body": "second", "op_id": "k4"}, "k4"))
t2 = store.resolve_ref("refs/cap/perspectives/Verso")
assert t1 and t2 and t1 != t2
mirror = "refs/replicas/verso"
a = S.advance_replica("carrier-1", mirror, t1, None)              # create
assert a["oid"] == t1 and store.resolve_ref(mirror) == t1, a
b = S.advance_replica("carrier-1", mirror, t2, t1)                # fast-forward
assert b["oid"] == t2 and store.resolve_ref(mirror) == t2, b
try:
    S.advance_replica("carrier-1", mirror, t1, t2)                # backwards: history would be rewritten
    raise SystemExit("FAIL: a non-fast-forward advance passed")
except NonFastForward:
    pass
try:
    S.advance_replica("carrier-1", mirror, t2, t1)                # stale expectation: CAS refuses
    raise SystemExit("FAIL: a stale CAS advance passed")
except StaleRef:
    pass
try:
    S.advance_replica("carrier-1", mirror, "0" * 40, t2)          # an oid this repo does not hold
    raise SystemExit("FAIL: an unknown oid was accepted")
except CapStoreError:
    pass
same = S.advance_replica("carrier-1", mirror, t2, t2)             # idempotent no-op
assert same["oid"] == t2 and store.resolve_ref(mirror) == t2
# a replica's CANON moves the same way — the structural writer bypasses the origin-only guard,
# but never the fast-forward law: a canon at C0 cannot be moved to an unrelated commit
c0 = store.resolve_ref(store.canon_ref)
try:
    S.advance_replica("carrier-1", store.canon_ref, t2, c0)   # t2 does not descend from c0
    raise SystemExit("FAIL: canon was moved to an unrelated history")
except NonFastForward:
    pass
assert store.resolve_ref(store.canon_ref) == c0
trail = audit.events(op="advance_replica")
assert [e["outcome"] for e in trail].count("ok") == 3 and \
       sum(1 for e in trail if str(e["outcome"]).startswith("error:")) == 4, [e["outcome"] for e in trail]
assert all(e["actor"] == "carrier-1" for e in trail)
print("door 2 replica      OK (create, fast-forward, refuse backwards / stale / unknown / unrelated-canon, idempotent; 7 audit rows under the carrier)")

print("\nOK -- the stacks stand alone: two doors and a shelf, store law behind the door, no transport in the process.")
