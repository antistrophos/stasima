# SPDX-License-Identifier: Apache-2.0
"""Run the suite.  python run_tests.py [-j N] [-k SUBSTR ...] [--serial]

Each *_test.py is a standalone script (its own temp repo, its own asserts, exit 0 = pass); this runner
just runs them all. Since 0.2.1 it runs them in PARALLEL by default (-j, default min(4, cpus)) — the
tests share nothing but the machine, and the git subprocesses they spawn are where the time goes,
so four at once is roughly a 3x wall-clock win — prints each test's wall time, and takes -k filters
(substrings of the file name) so one test or one family can be run alone. --serial (or -j 1) is the
0.2.0 behavior, useful when a failure needs a quiet machine to read.
"""
import argparse
import glob
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

try:   # Windows consoles default to cp1252; a test that prints utf-8 (✓, em dash, box chars) would
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # otherwise crash the runner on the tail
except Exception:
    pass

ap = argparse.ArgumentParser(description="run the stasima test suite")
ap.add_argument("-j", type=int, default=min(4, os.cpu_count() or 1), help="parallel tests (default min(4, cpus))")
ap.add_argument("-k", action="append", default=[], help="only tests whose file name contains SUBSTR (repeatable)")
ap.add_argument("--serial", action="store_true", help="one at a time (same as -j 1)")
args = ap.parse_args()
workers = 1 if args.serial else max(1, args.j)

here = os.path.dirname(os.path.abspath(__file__))
# Every test scratches in tempfile.mkdtemp() and none cleans up (bare repos, SQLite files). Left to
# the OS temp dir, a suite run leaves ~24 directories behind — 2,359 of them and 26 MB after three
# months on the build machine. So the runner gives the whole run ONE temp root and removes it at the
# end: the tests' mkdtemp() honors TEMP/TMP/TMPDIR, so they land inside it without knowing.
run_tmp = tempfile.mkdtemp(prefix="stasima-suite-")
env = {**os.environ, "PYTHONIOENCODING": "utf-8",   # each test's own stdout is utf-8, not the OS codepage
       "TEMP": run_tmp, "TMP": run_tmp, "TMPDIR": run_tmp}


def _unlock_and_retry(func, path, _exc):
    # git marks its object files read-only, and on Windows rmtree refuses those; clear the bit, retry
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass   # a file a straggling child still holds: leave it, the root's name says what it was


def sweep(root):
    if sys.version_info >= (3, 12):
        shutil.rmtree(root, onexc=_unlock_and_retry)
    else:  # pragma: no cover
        shutil.rmtree(root, onerror=lambda f, p, e: _unlock_and_retry(f, p, e[1]))


def run_one(path):
    t0 = time.monotonic()
    r = subprocess.run([sys.executable, path], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    return path, r.returncode, time.monotonic() - t0, (r.stdout + r.stderr)


tests = sorted(glob.glob(os.path.join(here, "*_test.py")))
if args.k:
    tests = [t for t in tests if any(k in os.path.basename(t) for k in args.k)]
if not tests:
    raise SystemExit("no tests matched")
failed, timings = [], []
t_suite = time.monotonic()
try:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for path, rc, secs, out in pool.map(run_one, tests):
            name = os.path.basename(path)
            timings.append((secs, name))
            print(f"{name:<24} {'PASS' if rc == 0 else 'FAIL'}  {secs:6.1f}s", flush=True)
            if rc != 0:
                failed.append(name)
                tail = out.splitlines()[-8:]
                print("    " + "\n    ".join(tail))
finally:
    # best effort: a test that left a server child alive could still hold a file open; the root is
    # named so a stray one is recognizable, and the next run does not depend on this one's removal
    sweep(run_tmp)
    if os.path.exists(run_tmp):
        print(f"(note: {run_tmp} could not be fully removed — a child still held a file)")
wall = time.monotonic() - t_suite
slowest = ", ".join(f"{n} {s:.0f}s" for s, n in sorted(timings, reverse=True)[:3])
print(f"\n{len(tests) - len(failed)}/{len(tests)} passed in {wall:.0f}s wall "
      f"({sum(s for s, _ in timings):.0f}s of test time, -j {workers}; slowest: {slowest})"
      + (f" — FAILED: {failed}" if failed else ""))
sys.exit(1 if failed else 0)
