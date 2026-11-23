# SPDX-License-Identifier: Apache-2.0
"""
Proves the audit subsystem standalone: hash chain + verify + tamper-detection, read-state as
append-only events, reconciliation from git (the git-first-then-audit recovery), and the
canon-land git anchor witnessing SQLite tampering.
"""
import os
import subprocess as sp
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stasima.local_capstore import LocalCapStore, Identity
from stasima.audit_log import SqliteAuditLog, reconcile_from_git, anchor_audit_head, verify_against_anchor

def persp(i): return f"refs/cap/perspectives/{i}"

# ============================================================ 1. chain, read-state, tamper
print("== chain integrity + read-state + tamper ==")
a = SqliteAuditLog(":memory:")
a.append("research-2", "entry_write", target_ref=persp("research-2"), op_id="op-1", result_oid="oid1")
a.append("research-2", "message_send", target_path="messages/m-1.md", op_id="op-2", result_oid="oid2",
         detail={"recipients": ["research-7"]})
e3 = a.append("research-7", "entry_write", target_ref=persp("research-7"), op_id="op-3", outcome="error:StaleRef")
ok, bad = a.verify()
head_ok = a.head() == e3["hash"]   # capture before append_read moves the head
print("  verify clean:", (ok, bad), "| head==last:", head_ok)

a.append_read("research-7", "messages/m-1.md")
print("  is_read r-7:", a.is_read("research-7", "messages/m-1.md"),
      "| is_read recto:", a.is_read("recto", "messages/m-1.md"))

a.conn.execute("UPDATE audit_events SET actor='mallory' WHERE seq=1")  # out-of-band tamper
a.conn.commit()
ok2, bad2 = a.verify()
print("  verify after tamper:", (ok2, bad2))

assert (ok, bad) == (True, None) and head_ok
assert a.is_read("research-7", "messages/m-1.md") and not a.is_read("recto", "messages/m-1.md")
assert ok2 is False and bad2 == 1

# ============================================================ 2. reconcile from git
print("\n== reconcile (git-first-then-audit recovery) ==")
work = tempfile.mkdtemp(prefix="cap-audit-")
gd = os.path.join(work, "stasima.git")
sp.run(["git", "init", "--bare", "-q", gd], check=True)
store = LocalCapStore(gd, approvers={"practitioner"})

ref = persp("research-2")
ra = store.commit(ref, {"practice/a.md": b"alpha"}, "KIP a", Identity("research-2"),
                  expected_parent=None, op_id="op-a")
rb = store.commit(ref, {"practice/b.md": b"beta"}, "KIP b", Identity("research-2"),
                  expected_parent=ra.oid, op_id="op-b")

audit = SqliteAuditLog(":memory:")
audit.append("research-2", "entry_write", target_ref=ref, op_id="op-a", result_oid=ra.oid)  # op-a logged
# op-b NOT logged — simulate a crash after the commit, before the audit append

n = reconcile_from_git(store, audit)
backfilled = [e["op_id"] for e in audit.events(op="reconciled_commit")]
print("  backfilled:", n, backfilled, "| verify:", audit.verify())
assert n == 1 and backfilled == ["op-b"]
assert audit.verify() == (True, None)

# ============================================================ 3. git anchor witnesses SQLite tamper
print("\n== canon-land anchor vs SQLite tamper ==")
anchor = anchor_audit_head(store, audit)
print("  anchored:", anchor)
print("  verify_against_anchor (intact):", verify_against_anchor(store, audit))
assert verify_against_anchor(store, audit) is True

audit.conn.execute("UPDATE audit_events SET actor='mallory' WHERE seq=1")  # tamper after anchoring
audit.conn.commit()
print("  verify_against_anchor (tampered):", verify_against_anchor(store, audit))
assert verify_against_anchor(store, audit) is False

# ============================================================ 4. two readers at the same moment
print("\n== two seats read the log at once ==")
shared = SqliteAuditLog(":memory:")
seats = [f"seat{n:03d}" for n in range(200)]
for s in seats:
    for k in range(3):
        shared.append(s, "canon_reconcile", result_oid=f"{s}-oid-{k}")     # the seat's canon cursor
        shared.append_read(s, f"messages/for-{s}-{k}.md")
alone = {s: shared.latest(op="canon_reconcile", actor=s) for s in seats}
wrong, gate = [], threading.Barrier(2)


def reader(offset):
    for n in range(100):
        s = seats[offset + n]
        for _ in range(10):
            gate.wait()
            try:
                cursor = shared.latest(op="canon_reconcile", actor=s)
                seen = shared.is_read(s, f"messages/for-{s}-1.md")
                mine = shared.events(op="read_receipt", actor=s)
            except Exception as err:                                      # noqa: BLE001 — any failure is the finding
                wrong.append((s, repr(err)))
                continue
            if cursor != alone[s] or not seen or len(mine) != 3 or any(e["actor"] != s for e in mine):
                wrong.append((s, "another seat's answer"))


pair = [threading.Thread(target=reader, args=(o,)) for o in (0, 100)]
[th.start() for th in pair]
[th.join() for th in pair]
print("  2000 paired reads, wrong or failed:", len(wrong))
assert not wrong, (len(wrong), wrong[:3])

# ============================================================ 5. three processes, one audit file
# The service, the cockpit and the admin CLI each open the same file. The thread lock covers one
# process; the tail read and the insert must be one transaction or two processes take the same seq.
print("\n== three processes append to one audit file ==")
here = os.path.dirname(os.path.abspath(__file__))
dbf = os.path.join(tempfile.mkdtemp(prefix="cap-audit-procs-"), "audit.sqlite")
SqliteAuditLog(dbf).append("setup", "start")
worker = ("import sys; sys.path.insert(0, sys.argv[1]); from stasima.audit_log import SqliteAuditLog; "
          "log = SqliteAuditLog(sys.argv[2]); "
          "[log.append(sys.argv[3], 'entry_write', op_id=sys.argv[3] + '-' + str(n)) for n in range(300)]")
procs = [sp.Popen([sys.executable, "-c", worker, here, dbf, who], stderr=sp.PIPE)
         for who in ("service", "cockpit", "cli")]
errors = [p.communicate()[1].decode("utf-8", "replace") for p in procs]
print("  processes that failed:", sum(p.returncode != 0 for p in procs))
assert all(p.returncode == 0 for p in procs), [e.strip().splitlines()[-1] for e in errors if e.strip()]
shared_file = SqliteAuditLog(dbf)
assert shared_file.count() == 901 and shared_file.verify() == (True, None), (shared_file.count(), shared_file.verify())

print("\nOK -- chain, read-state, reconcile, git-anchored tamper-evidence, readers at once, and writers "
      "in three processes all verified.")
