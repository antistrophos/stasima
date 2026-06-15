# SPDX-License-Identifier: Apache-2.0
"""Run the whole suite: python run_tests.py  (each *_test.py is standalone; this just runs them all)."""
import glob
import os
import subprocess
import sys

try:   # Windows consoles default to cp1252; a test that prints utf-8 (✓, em dash, box chars) would
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # otherwise crash the runner on the tail
except Exception:
    pass

here = os.path.dirname(os.path.abspath(__file__))
env = {**os.environ, "PYTHONIOENCODING": "utf-8"}   # so each test's own stdout is utf-8, not the OS codepage
tests = sorted(glob.glob(os.path.join(here, "*_test.py")))
failed = []
for t in tests:
    name = os.path.basename(t)
    r = subprocess.run([sys.executable, t], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    print(f"{name:<22} {'PASS' if r.returncode == 0 else 'FAIL'}")
    if r.returncode != 0:
        failed.append(name)
        tail = (r.stdout + r.stderr).splitlines()[-8:]
        print("    " + "\n    ".join(tail))
print(f"\n{len(tests) - len(failed)}/{len(tests)} passed" + (f" — FAILED: {failed}" if failed else ""))
sys.exit(1 if failed else 0)
