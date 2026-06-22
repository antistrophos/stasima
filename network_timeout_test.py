# SPDX-License-Identifier: Apache-2.0
"""
The network-timeout decoupling — the regression test for the backup/mirror/sync fix.

The bug: every git op shared ONE timeout, the interactive hang-guard (git_timeout, ~2s under stdio).
That guard is right for a sub-second LOCAL op (a hang there means a second server contending on the
repo), but WRONG for a NETWORK/batch op (push/fetch/ls-remote) that legitimately takes seconds-to-
minutes — so a real backup aborted at 2s with a misleading "second server" error. The fix routes the
four network methods (push_all / fetch_all / mirror_push / verify_sync) through git_network_timeout
instead, and leaves local ops on the tight interactive guard.

This proves the decoupling in BOTH directions, deterministically: it spies on the timeout each git
subcommand is invoked with — so it needs no slow remote and cannot flake on wall-clock timing.
- every network op (push/fetch/ls-remote) carries git_network_timeout, never the interactive guard;
- no local op borrows the network timeout.
The test that would have CAUGHT the original bug.
"""
import os
import subprocess as sp
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stasima.local_capstore import LocalCapStore, Identity
from stasima.entries import compose_entry

entry = lambda title, body: compose_entry({"type": "kno", "title": title, "status": "active"}, body).encode()

GT, GNT = 1.5, 99.0                      # distinct sentinels — a captured timeout names which guard ran
NET = {"push", "fetch", "ls-remote"}     # the only git ops that actually round-trip to a remote

work = tempfile.mkdtemp(prefix="cap-nettimeout-")
gd = os.path.join(work, "stasima.git")
sp.run(["git", "init", "--bare", "-q", gd], check=True)
store = LocalCapStore(gd, approvers={"practitioner"}, git_timeout=GT, git_network_timeout=GNT)
assert store.git_timeout == GT and store.git_network_timeout == GNT, "store carries both timeouts, distinct"

store.bootstrap_canon({"practice/seed.md": entry("Seed", "the seed")}, "bootstrap")   # something to push

# spy: record (git-subcommand, timeout-arg) for every git invocation, then call through (real git runs)
calls = []
orig_run = store._run
def spy(*args, **kwargs):
    calls.append((args[0] if args else None, kwargs.get("timeout")))
    return orig_run(*args, **kwargs)
store._run = spy

# --- LOCAL ops keep the interactive guard: a commit's git calls pass timeout=None (which _run then
#     resolves to git_timeout), and NONE of them borrows the network timeout ---
mark = len(calls)
store.commit("refs/cap/perspectives/tester", {"practice/notes.md": entry("Notes", "notes")},
             "kip", Identity("tester"), expected_parent=None, op_id="op-int")
local = calls[mark:]
assert local, "the commit ran git"
assert all(t is None for _c, t in local), f"local ops must stay on the interactive guard, got {local}"
assert all(c not in NET for c, _t in local), "a commit does no network ops"
print(f"  local commit: {len(local)} git ops, all on the interactive guard (timeout=None)")

# --- a remote to push to ---
remote = os.path.join(work, "remote.git")
sp.run(["git", "init", "--bare", "-q", remote], check=True)

# --- push_all (the `admin backup` primitive): push + verify_sync(ls-remote) on git_network_timeout ---
mark = len(calls)
store.set_remote("backup", remote)
store.push_all("backup")
pushed = calls[mark:]
net = [(c, t) for c, t in pushed if c in NET]
assert {c for c, _ in net} >= {"push", "ls-remote"}, f"push_all should push then verify, got {net}"
assert all(t == GNT for _c, t in net), f"push_all network ops must use git_network_timeout, got {net}"
assert all(t is None for c, t in pushed if c == "remote"), "set_remote's own probe stays interactive"
print(f"  push_all: {sorted({c for c, _ in net})} on git_network_timeout ({GNT}); set_remote probe interactive")

# --- fetch_all ---
mark = len(calls)
store.fetch_all("backup")
fetched = [(c, t) for c, t in calls[mark:] if c == "fetch"]
assert fetched and all(t == GNT for _c, t in fetched), f"fetch_all must use git_network_timeout, got {fetched}"
print(f"  fetch_all: fetch on git_network_timeout ({GNT})")

# --- mirror_push (the off-machine `admin mirror` primitive): push + verify on git_network_timeout ---
mremote = os.path.join(work, "mirror.git")
sp.run(["git", "init", "--bare", "-q", mremote], check=True)
mark = len(calls)
store.mirror_push("mir", mremote)
mirrored = [(c, t) for c, t in calls[mark:] if c in NET]
assert mirrored and all(t == GNT for _c, t in mirrored), f"mirror_push network ops must use GNT, got {mirrored}"
print(f"  mirror_push: {sorted({c for c, _ in mirrored})} on git_network_timeout ({GNT})")

# --- the regression itself, stated as an invariant over EVERY git op the test ran ---
net_all = [(c, t) for c, t in calls if c in NET]
assert net_all, "the test must have exercised network ops"
offenders = [(c, t) for c, t in net_all if t != GNT]
assert not offenders, f"REGRESSION: a network op fell back to a non-network timeout: {offenders}"
borrowers = [(c, t) for c, t in calls if c not in NET and t == GNT]
assert not borrowers, f"REGRESSION: a local op borrowed the network timeout: {borrowers}"

print("\nOK -- network-timeout decoupling: push/fetch/ls-remote use git_network_timeout; "
      "local ops keep the interactive guard. The 2s-backup bug cannot recur.")
