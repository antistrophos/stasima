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
from mcp.client import Client as connect   # v2: the in-process client — one Client, one connection  # noqa: E402

# family (the tool name's first segment) -> section title, in the order the reference reads best;
# an unmapped family still renders (under "Other"), so a new tool cannot vanish
FAMILIES = [
    ("seat", "Seat — identity and arrival"),
    ("canon", "Canon — the shared branch and reconcile"),
    ("entry", "Entry — write, read, list, search, history"),
    ("vantage", "Vantage — the context an entry was written against"),
    ("message", "Message — the inbox"),
    ("proposal", "Proposal — the path into canon, and the practitioner's relay"),
    ("thread", "Thread"),
    ("term", "Term — the argot dictionary"),
    ("server", "Server"),
]
# the order the glossary lists the tools in (technical/suites/eurotas/glossary.md); unknown names follow
ORDER = ["seat_announce", "seat_whoami", "seat_list", "seat_state",
         "canon_state", "canon_diff", "canon_reconcile",
         "entry_write", "entry_read", "entry_list", "entry_search", "entry_history",
         "vantage_write", "vantage_list",
         "message_send", "message_inbox", "message_unread_count", "message_mark_read",
         "proposal_append_entry", "proposal_retract_path", "proposal_preview", "proposal_list", "proposal_close",
         "proposal_stage", "proposal_land", "proposal_unstage",
         "thread_list", "term_list", "server_stats"]
CLASSES = {
    "replica": "a read any replica holding the refs can answer, later, elsewhere",
    "process": "answered only by the process the seat is connected to",
    "origin": "mutates origin state (a ref or the audit log); needs a live lane to origin",
    "relay": "origin, plus the practitioner's TOTP code in the conversation",
}

MIN_EXPECTED = 29   # the generator fails loudly if tools go missing rather than emitting a partial reference (29 = the 0.1.5 dedup floor)


def _suite_version() -> str:
    # the version's single home is stasima/__init__.py (pyproject reads it dynamically)
    try:
        text = open(os.path.join(ROOT, "stasima", "__init__.py"), encoding="utf-8").read()
        m = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.M)
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
        return [(t.name, t.description or "", t.input_schema or {}, (getattr(t, "meta", None) or {}).get("class", ""))
                for t in result.tools]


def generate(out_path: str) -> int:
    tools = anyio.run(_collect)
    if len(tools) < MIN_EXPECTED:
        raise SystemExit(f"expected at least {MIN_EXPECTED} tools, found {len(tools)} — refusing to emit a partial reference")
    by_name = {name: (desc, schema, cls) for name, desc, schema, cls in tools}
    order = {fam: i for i, (fam, _) in enumerate(FAMILIES)}
    grouped = {}
    for n in by_name:
        grouped.setdefault(n.split("_", 1)[0], []).append(n)
    sections = sorted(grouped, key=lambda f: (order.get(f, len(order)), f))
    rank = {n: i for i, n in enumerate(ORDER)}

    def in_order(names):
        return sorted(names, key=lambda x: (rank.get(x, len(rank)), x))

    lines = [
        "# Tool reference",
        "",
        f"*Generated from the live tool registry by [`docs/gen_tools.py`](gen_tools.py) — do not edit by hand; "
        f"regenerate with `python docs/gen_tools.py`. Suite version at generation: **{_suite_version()}**. "
        f"{len(tools)} tools. This page is the wire contract: names, parameters, and behavior exactly as a "
        f"connecting seat receives them. Your deployment's canon governs practice-level conventions "
        f"(state lines, conduct, naming); this page documents the machinery.*",
        "",
        "Tool names are `<family>_<verb>` (an act) or `<family>_<view>` (a named read). Every tool states its "
        "**class** — whether the call tolerates being answered later, from a replica, or needs a live lane to origin:",
        "",
    ]
    for cls, meaning in CLASSES.items():
        lines.append(f"- `{cls}` — {meaning}")
    lines.append("")
    lines.append("| tool | class | what it does |")
    lines.append("|---|---|---|")
    for fam in sections:
        for n in in_order(grouped[fam]):
            desc, _, cls = by_name[n]
            first = " ".join(desc.split()).split(". ")[0].rstrip(".") + "."
            lines.append(f"| `{n}` | {cls} | {first} |")
    lines.append("")
    titles = dict(FAMILIES)
    for fam in sections:
        lines.append(f"## {titles.get(fam, fam.capitalize())}")
        lines.append("")
        for n in in_order(grouped[fam]):
            desc, schema, cls = by_name[n]
            lines.append(f"### `{n}` — {cls}")
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
