# SPDX-License-Identifier: Apache-2.0
"""
HTTP transport, end to end: boot the real server subprocess under STASIMA_CONFIG with
transport="http", connect with the MCP streamable-http client, initialize, list tools, announce.
Also: the bind-address guard (loopback/tailnet allowed; wider binds refused until 1.1 auth).
"""
import os
import socket
import subprocess as sp
import sys
import tempfile
import time

import anyio

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from stasima.config import Config, ConfigError
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# ---- bind-address guard (the structural "no outside exposure until 1.1") ----
def rejected(**kw):
    try:
        Config(git_dir="/x/r.git", transport="http", **kw).validate()
        return False
    except ConfigError:
        return True

Config(git_dir="/x/r.git", transport="http", http_host="127.0.0.1").validate()
Config(git_dir="/x/r.git", transport="http", http_host="localhost").validate()
Config(git_dir="/x/r.git", transport="http", http_host="100.101.1.5").validate()   # tailnet CGNAT
assert rejected(http_host="0.0.0.0"), "0.0.0.0 must be refused (no auth yet)"
assert rejected(http_host="192.168.1.50"), "LAN bind must be refused (no auth yet)"
assert rejected(http_host="example.com"), "hostnames other than localhost refused"
assert rejected(http_port=0), "port 0 refused"
print("bind guard          OK (loopback+tailnet allowed; LAN/0.0.0.0 refused until 1.1)")

# ---- live server over HTTP ----
work = tempfile.mkdtemp(prefix="stasima-http-")
gd = os.path.join(work, "stasima.git")
sp.run(["git", "init", "--bare", "-q", gd], check=True)
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
cfgpath = os.path.join(work, "stasima.toml")
with open(cfgpath, "w", encoding="utf-8") as f:
    f.write(f'git_dir = "{gd.replace(os.sep, "/")}"\ntransport = "http"\nhttp_port = {port}\n')

env = dict(os.environ, STASIMA_CONFIG=cfgpath)
proc = sp.Popen([sys.executable, "-m", "stasima.cap_server"], env=env, cwd=HERE,
                stdout=sp.DEVNULL, stderr=sp.DEVNULL)
try:
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            break
        except OSError:
            if proc.poll() is not None:
                raise SystemExit(f"server exited early: {proc.returncode}")
            time.sleep(0.3)
    else:
        raise SystemExit("server never opened the port")
    print(f"server up           OK (127.0.0.1:{port})")

    async def main():
        async with streamablehttp_client(f"http://127.0.0.1:{port}/mcp") as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = sorted(t.name for t in (await session.list_tools()).tools)
                assert "announce" in tools and "stage_approve" in tools, tools
                print(f"tools over http     OK ({len(tools)} tools)")
                res = await session.call_tool("announce", {"instance_id": "epode"})
                text = "".join(getattr(c, "text", "") for c in res.content)
                assert "Welcome to Stasima, epode." in text, text[:120]
                print("announce over http  OK ->", "Welcome to Stasima, epode.")

    anyio.run(main)

    # ---- Phase B: per-SESSION sticky binding over real HTTP sessions ----
    # Two client sessions against ONE server process: each learns its own seat (under the old
    # process-sticky, the second seat would refuse — the trunk problem, now dissolved), and a
    # cross-claim inside a bound session still refuses with the learned name in the error.
    async def binding_over_sessions():
        async with streamablehttp_client(f"http://127.0.0.1:{port}/mcp") as (r1, w1, _):
            async with ClientSession(r1, w1) as s1:
                await s1.initialize()
                async with streamablehttp_client(f"http://127.0.0.1:{port}/mcp") as (r2, w2, _):
                    async with ClientSession(r2, w2) as s2:
                        await s2.initialize()
                        a = await s1.call_tool("kip_commit", {"instance_id": "SeatA", "domain": "state",
                                                              "slug": "a1", "body": "a", "op_id": "ha1"})
                        assert not getattr(a, "isError", False), \
                            "".join(getattr(c, "text", "") for c in a.content)[:200]
                        b = await s2.call_tool("kip_commit", {"instance_id": "SeatB", "domain": "state",
                                                              "slug": "b1", "body": "b", "op_id": "hb1"})
                        assert not getattr(b, "isError", False), \
                            "two sessions must bind two seats independently: " + \
                            "".join(getattr(c, "text", "") for c in b.content)[:200]
                        x = await s1.call_tool("kip_commit", {"instance_id": "SeatB", "domain": "state",
                                                              "slug": "x1", "body": "x", "op_id": "hx1"})
                        xt = "".join(getattr(c, "text", "") for c in x.content)
                        assert getattr(x, "isError", False) and "SeatA" in xt, xt[:200]
                        w = await s2.call_tool("whoami", {"instance_id": "SeatB"})
                        wt = "".join(getattr(c, "text", "") for c in w.content)
                        assert "SeatB" in wt and "session" in wt, wt[:200]
        print("session binding     OK (two sessions, two seats; cross-claim refused with the name)")

    anyio.run(binding_over_sessions)

    # DNS-rebinding protection: a request whose Host isn't the bind/allowlist is refused
    import httpx
    r = httpx.post(f"http://127.0.0.1:{port}/mcp", headers={"Host": "evil.example.com"},
                   json={"jsonrpc": "2.0", "method": "initialize", "id": 1}, timeout=10)
    assert r.status_code in (400, 403, 421), r.status_code
    print(f"host-spoof reject   OK (HTTP {r.status_code} for Host: evil.example.com)")
finally:
    proc.terminate()
    proc.wait(timeout=10)

print("\nOK -- http transport: bind guard + live server + real MCP client round-trip.")
