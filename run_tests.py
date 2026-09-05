# SPDX-License-Identifier: Apache-2.0
"""Run the whole suite: python run_tests.py  (each *_test.py is standalone; this just runs them all)."""
import glob
import os
import shutil
import stat
import subprocess
import sys
import tempfile

try:   # Windows consoles default to cp1252; a test that prints utf-8 (✓, em dash, box chars) would
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # otherwise crash the runner on the tail
except Exception:
    pass

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
tests = sorted(glob.glob(os.path.join(here, "*_test.py")))
failed = []
try:
    for t in tests:
        name = os.path.basename(t)
        r = subprocess.run([sys.executable, t], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env)
        print(f"{name:<22} {'PASS' if r.returncode == 0 else 'FAIL'}")
        if r.returncode != 0:
            failed.append(name)
            tail = (r.stdout + r.stderr).splitlines()[-8:]
            print("    " + "\n    ".join(tail))
finally:
    # best effort: a test that left a server child alive could still hold a file open; the root is
    # named so a stray one is recognizable, and the next run does not depend on this one's removal
    sweep(run_tmp)
    if os.path.exists(run_tmp):
        print(f"(note: {run_tmp} could not be fully removed — a child still held a file)")
print(f"\n{len(tests) - len(failed)}/{len(tests)} passed" + (f" — FAILED: {failed}" if failed else ""))
sys.exit(1 if failed else 0)
