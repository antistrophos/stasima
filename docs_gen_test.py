# SPDX-License-Identifier: Apache-2.0
"""
The tool-reference generator stays alive: docs/tools.md is DERIVED from the live registry (the
drift-killer for the doc-rot class the 0.1.3 review caught), so the generator itself must not rot.
Generates into a temp file and asserts the wire contract made it through.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs"))
import gen_tools  # noqa: E402

out = os.path.join(tempfile.mkdtemp(prefix="stasima-docgen-"), "tools.md")
n = gen_tools.generate(out)
assert n >= gen_tools.MIN_EXPECTED, f"tool count regressed: {n}"

text = open(out, encoding="utf-8").read()
# every registered tool renders as a heading; the fixed floor keeps a silent dropout loud
assert text.count("### `") == n, "every tool must render exactly once"
# the contracts this release added must ride the generated page (they live in docstrings/schemas)
for must in ("horizon", "resolve", "include_superseded", "detail", "with_vantages",
             "supersedes", "### `stage_approve`", "### `vap_for`", "recovery"):
    assert must in text, f"generated reference is missing {must!r}"
print(f"OK -- tool reference generates: {n} tools, contracts present, derived-not-authored.")
