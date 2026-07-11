# SPDX-License-Identifier: Apache-2.0
"""
Real stdio transport, end to end: spawn the server the way Claude Desktop does (python -m over
stdio) and drive read-only tools through the MCP stdio client. This is the path that hung on
Windows when git subprocesses inherited the server's JSON-RPC stdin pipe — every read tool stalled
the event loop until the client timed out. The fix (DEVNULL stdin for input-less git calls) lives
in local_capstore._run; this guards it.

Note: the original hang is Windows-specific (the Proactor stdio loop), so on Linux CI this passes
regardless — but it exercises the real stdio transport, which the in-memory and HTTP tests do not,
and on a Windows dev machine it catches a regression hard.
"""
import os
import subprocess as sp
import sys
import tempfile

import anyio

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

work = tempfile.mkdtemp(prefix="stasima-stdio-")
gd = os.path.join(work, "stasima.git")
sp.run(["git", "init", "--bare", "-q", gd], check=True)
# seed a canon so build_orientation (announce's slow path) actually reads blobs
sys.path.insert(0, HERE)
from stasima.local_capstore import LocalCapStore
from stasima.entries import compose_entry
store = LocalCapStore(gd, approvers={"practitioner"})
store.bootstrap_canon(
    {"technical/orientation/welcome.md": compose_entry(
        {"type": "ori", "title": "Welcome", "status": "active"}, "Welcome.").encode()},
    "bootstrap")

cfg = os.path.join(work, "stasima.toml")
with open(cfg, "w", encoding="utf-8") as f:
    f.write(f'git_dir = "{gd.replace(os.sep, "/")}"\ntransport = "stdio"\n')

params = StdioServerParameters(command=sys.executable, args=["-m", "stasima.cap_server"],
                               env=dict(os.environ, STASIMA_CONFIG=cfg, PYTHONPATH=HERE))


async def main():
    # a generous ceiling: the bug made this never return; correct behavior is a second or two
    with anyio.move_on_after(45) as scope:
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                tools = (await s.list_tools()).tools
                assert len(tools) == 33, f"expected 33 tools over stdio, got {len(tools)}"  # +thread_scry, +arg_scry, +propose_close
                # the calls that inherited-stdin used to hang: read-only, git-backed
                res = await s.call_tool("announce", {"instance_id": "stdio-probe"})
                txt = "".join(getattr(c, "text", "") for c in res.content)
                assert "Welcome" in txt, txt[:120]
                for name, arg in [("whoami", {"instance_id": "stdio-probe"}),
                                  ("canon_head", {}), ("list_instances", {})]:
                    rr = await s.call_tool(name, arg)
                    assert not getattr(rr, "isError", False), (name, rr)

                # the WRITE + DELETE path over real stdio (Lintel found propose_retract hanging here —
                # the deletion plumbing runs git the read tools don't). reconcile, propose an entry +
                # log entry, then retract the log entry; all must return promptly.
                await s.call_tool("canon_diff", {"instance_id": "stdio-probe"})
                await s.call_tool("sup_reconcile", {"instance_id": "stdio-probe", "body": "read"})
                await s.call_tool("propose", {"instance_id": "stdio-probe", "proposal_id": "p-stdio",
                                              "domain": "practice", "slug": "x", "body": "x", "op_id": "ps-1"})
                await s.call_tool("propose", {"instance_id": "stdio-probe", "proposal_id": "p-stdio",
                                              "domain": "meta/log", "slug": "1", "body": "::1", "op_id": "ps-2",
                                              "type": "log", "seq": "1"})
                rt = await s.call_tool("propose_retract", {"instance_id": "stdio-probe",
                                       "proposal_id": "p-stdio", "path": "meta/log/1.md", "op_id": "ps-3"})
                assert not getattr(rt, "isError", False), ("propose_retract", rt)
                print(f"stdio transport OK: {len(tools)} tools; read, propose, AND propose_retract all returned")
    if scope.cancelled_caught:
        raise SystemExit("FAIL: stdio tool calls hung (the inherited-stdin regression is back)")


anyio.run(main)
print("OK -- real stdio transport: no hang, read tools return promptly.")
