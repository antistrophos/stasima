# SPDX-License-Identifier: Apache-2.0
"""
Generate docs/tools.md from the LIVE tool registry — the wire contract, exactly as a connecting
instance sees it (an in-memory client's list_tools() over the production server assembly).

A reference derived from the code cannot drift from it: the doc-rot class the 0.1.3 release review
caught (five hand-kept homes for tool behavior, each aging separately) is structurally removed for
this page. Regenerate on any tool change:  python docs/gen_tools.py

Output is deterministic (no timestamps) so regeneration produces clean diffs.
"""
import os
import re
import subprocess as sp
import sys
import tempfile

import anyio

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from stasima.config import Config                     # noqa: E402
from stasima.cap_server import server_from_config     # noqa: E402
from mcp.shared.memory import create_connected_server_and_client_session as connect  # noqa: E402

# tool -> section; an unmapped tool still renders (under "Other"), so a new tool cannot vanish
SECTIONS = [
    ("Arrive & orient", ["announce", "orientation", "canon_head", "canon_state", "whoami", "list_instances"]),
    ("Author — and the fold", ["kip_commit", "vap_record"]),
    ("Read", ["kip_get", "list_entries", "my_perspective", "kip_history"]),
    ("Search (MAP)", ["map_search"]),
    ("Vantages (VAP)", ["vap_for"]),
    ("Messages (IMP)", ["imp_send", "imp_check", "imp_flags", "imp_mark_read"]),
    ("Coherence (SUP)", ["canon_diff", "sup_reconcile", "sup_state", "sup_who"]),
    ("Propose & track", ["propose", "propose_retract", "proposal_status", "conflict_preview", "list_proposals"]),
    ("Approval relay (the airlock)", ["stage_approve", "land_approve", "stage_revert"]),
]

MIN_EXPECTED = 29   # the generator fails loudly if tools go missing rather than emitting a partial reference (29 = the 0.1.5 dedup floor)


def _suite_version() -> str:
    try:
        text = open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8").read()
        m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
        return m.group(1) if m else "unknown"
    except OSError:
        return "unknown"


def _schema_type(prop: dict) -> str:
    if "type" in prop:
        t = prop["type"]
        if t == "array":
            item = prop.get("items", {})
            return f"list[{item.get('type', 'any')}]"
        return t
    if "anyOf" in prop:
        return " | ".join(_schema_type(p) for p in prop["anyOf"])
    return "any"


def _render_params(schema: dict) -> list:
    props = (schema or {}).get("properties", {})
    required = set((schema or {}).get("required", []))
    lines = []
    for name, prop in props.items():
        t = _schema_type(prop)
        if name in required:
            tail = "required"
        elif "default" in prop:
            d = prop["default"]
            tail = f"default `{d!r}`" if isinstance(d, str) else f"default `{d}`"
        else:
            tail = "optional"
        lines.append(f"- `{name}` ({t}, {tail})")
    return lines


async def _collect():
    work = tempfile.mkdtemp(prefix="stasima-doc-gen-")
    gd = os.path.join(work, "stasima.git")
    sp.run(["git", "init", "--bare", "-q", gd], check=True)
    cfg = Config(git_dir=gd)
    async with connect(server_from_config(cfg)) as client:
        result = await client.list_tools()
        return [(t.name, t.description or "", t.inputSchema or {}) for t in result.tools]


def generate(out_path: str) -> int:
    tools = anyio.run(_collect)
    if len(tools) < MIN_EXPECTED:
        raise SystemExit(f"expected at least {MIN_EXPECTED} tools, found {len(tools)} — refusing to emit a partial reference")
    by_name = {name: (desc, schema) for name, desc, schema in tools}

    lines = [
        "# Tool reference",
        "",
        f"*Generated from the live tool registry by [`docs/gen_tools.py`](gen_tools.py) — do not edit by hand; "
        f"regenerate with `python docs/gen_tools.py`. Suite version at generation: **{_suite_version()}**. "
        f"{len(tools)} tools. This page is the wire contract: names, parameters, and behavior exactly as a "
        f"connecting instance receives them. Your deployment's canon governs practice-level conventions "
        f"(state lines, conduct, naming); this page documents the machinery.*",
        "",
    ]
    seen = set()
    for section, names in SECTIONS:
        present = [n for n in names if n in by_name]
        if not present:
            continue
        lines.append(f"## {section}")
        lines.append("")
        for n in present:
            seen.add(n)
            desc, schema = by_name[n]
            lines.append(f"### `{n}`")
            lines.append("")
            lines.append(desc.strip())
            lines.append("")
            params = _render_params(schema)
            if params:
                lines.append("**Parameters**")
                lines.extend(params)
                lines.append("")
    leftovers = sorted(set(by_name) - seen)
    if leftovers:
        lines.append("## Other")
        lines.append("")
        for n in leftovers:
            desc, schema = by_name[n]
            lines.append(f"### `{n}`")
            lines.append("")
            lines.append(desc.strip())
            lines.append("")
            params = _render_params(schema)
            if params:
                lines.append("**Parameters**")
                lines.extend(params)
                lines.append("")
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    return len(tools)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "tools.md")
    n = generate(out)
    print(f"wrote {out} ({n} tools)")
