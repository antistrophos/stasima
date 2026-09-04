# SPDX-License-Identifier: Apache-2.0
"""
HTTP transport, end to end: boot the real server subprocess under STASIMA_CONFIG with
transport="http", connect with the SDK client in BOTH protocol eras (modern 2026-07-28 and the
handshake-era protocol the mcp-proxy bridge speaks), list tools, announce.
Also: the bind-address guard (loopback/tailnet allowed; wider binds refused until 1.1 auth), the
DNS-rebinding guard, and binding at PROCESS grain over a shared service — off (the honest shared
configuration: attribution rides every write, nothing binds), pinned (one seat's own door, enforced
over HTTP regardless of sessions), and the startup refusal of a shared service that could learn.
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
from mcp.client import Client   # v2: one client object; mode="legacy" speaks the handshake-era protocol

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


# ---- live servers over HTTP ----
def text(res):
    return "".join(getattr(c, "text", "") for c in res.content)


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    return port


def boot(extra_toml="", extra_env=None, expect_up=True):
    """Spawn the real server under a fresh bare repo + toml. Returns (proc, port, stderr_path)."""
    work = tempfile.mkdtemp(prefix="stasima-http-")
    gd = os.path.join(work, "stasima.git")
    sp.run(["git", "init", "--bare", "-q", gd], check=True)
    port = free_port()
    cfgpath = os.path.join(work, "stasima.toml")
    with open(cfgpath, "w", encoding="utf-8") as f:
        f.write(f'git_dir = "{gd.replace(os.sep, "/")}"\ntransport = "http"\nhttp_port = {port}\n{extra_toml}')
    env = dict(os.environ, STASIMA_CONFIG=cfgpath, **(extra_env or {}))
    errpath = os.path.join(work, "stderr.txt")
    err = open(errpath, "w", encoding="utf-8")
    proc = sp.Popen([sys.executable, "-m", "stasima.cap_server"], env=env, cwd=HERE,
                    stdout=sp.DEVNULL, stderr=err)
    if not expect_up:
        return proc, port, errpath
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            return proc, port, errpath
        except OSError:
            if proc.poll() is not None:
                err.close()
                with open(errpath, encoding="utf-8") as f:
                    raise SystemExit(f"server exited early: {proc.returncode}\n{f.read()[-2000:]}")
            time.sleep(0.3)
    raise SystemExit("server never opened the port")


def stop(proc):
    proc.terminate()
    proc.wait(timeout=10)


# ---- 1. the shared service, configured honestly: binding off ----
proc, port, _ = boot('binding_mode = "off"\n')
try:
    print(f"server up           OK (127.0.0.1:{port}, binding off)")
    url = f"http://127.0.0.1:{port}/mcp"

    async def arrive(session, label):
        tools = sorted(t.name for t in (await session.list_tools()).tools)
        assert "announce" in tools and "stage_approve" in tools, tools
        res = await session.call_tool("announce", {"instance_id": "epode"})
        assert "Welcome to Stasima, epode." in text(res), text(res)[:120]
        print(f"{label:<19} OK ({len(tools)} tools; announce -> Welcome to Stasima, epode.)")
        return tools

    async def main():
        # the modern protocol (2026-07-28: no handshake, no session, version in every request)
        async with Client(url) as session:
            modern = await arrive(session, "modern client")
        # the handshake-era protocol — what the mcp-proxy bridge speaks; a v2 server serves every
        # earlier revision, so the fleet's connector survives the port unchanged
        async with Client(url, mode="legacy") as session:
            legacy = await arrive(session, "legacy client")
        assert modern == legacy, "both protocol eras must see the same tool surface"

    anyio.run(main)

    # ---- binding at process grain, shared service OFF: two conversations, two seats, both
    # write; attribution rides each envelope; nothing binds and whoami says so plainly ----
    async def shared_off():
        async with Client(url, mode="legacy") as s1:
            async with Client(url, mode="legacy") as s2:
                a = await s1.call_tool("kip_commit", {"instance_id": "SeatA", "domain": "state",
                                                      "slug": "a1", "body": "a", "op_id": "ha1"})
                assert not a.is_error, text(a)[:200]
                b = await s2.call_tool("kip_commit", {"instance_id": "SeatB", "domain": "state",
                                                      "slug": "b1", "body": "b", "op_id": "hb1"})
                assert not b.is_error, text(b)[:200]
                w = await s2.call_tool("whoami", {"instance_id": "SeatB"})
                wt = text(w)
                assert '"mode": "off"' in wt and '"grain": "process"' in wt and '"bound_instance": null' in wt, wt[:300]
        print("shared service off  OK (two conversations, two seats write; whoami: mode off, grain process)")

    anyio.run(shared_off)

    # DNS-rebinding protection: a request whose Host isn't the bind/allowlist is refused
    import httpx
    r = httpx.post(url, headers={"Host": "evil.example.com"},
                   json={"jsonrpc": "2.0", "method": "initialize", "id": 1}, timeout=10)
    assert r.status_code in (400, 403, 421), r.status_code
    print(f"host-spoof reject   OK (HTTP {r.status_code} for Host: evil.example.com)")
finally:
    stop(proc)

# ---- 2. a shared service that COULD learn must refuse to start (the trunk problem, structural) ----
proc, port, errpath = boot("", expect_up=False)          # no binding_mode -> strict, unpinned
try:
    proc.wait(timeout=30)
finally:
    if proc.poll() is None:
        stop(proc)
with open(errpath, encoding="utf-8") as f:
    err = f.read()
assert proc.returncode != 0 and "no per-conversation session" in err, (proc.returncode, err[-600:])
print("shared+strict       OK (refused at startup; the error names the fix: off, or pin the seat)")

# ---- 3. a PINNED service: one seat's own door, enforced over HTTP with no session at all ----
proc, port, _ = boot("", extra_env={"STASIMA_INSTANCE": "SeatA"})
try:
    url = f"http://127.0.0.1:{port}/mcp"

    async def pinned():
        async with Client(url) as s:                        # modern protocol: no session exists
            ok = await s.call_tool("kip_commit", {"instance_id": "SeatA", "domain": "state",
                                                  "slug": "p1", "body": "a", "op_id": "hp1"})
            assert not ok.is_error, text(ok)[:200]
            x = await s.call_tool("kip_commit", {"instance_id": "SeatB", "domain": "state",
                                                 "slug": "p2", "body": "b", "op_id": "hp2"})
            assert x.is_error and "pinned to 'SeatA'" in text(x), text(x)[:200]
            w = text(await s.call_tool("whoami", {"instance_id": "SeatB"}))
            assert '"source": "pinned"' in w and '"grain": "process"' in w and '"match": false' in w, w[:300]
        print("pinned service      OK (SeatA writes; SeatB's claim refused with the pinned name; no session needed)")

    anyio.run(pinned)
finally:
    stop(proc)

print("\nOK -- http transport: bind guard + both protocol eras + process-grain binding (off / refused / pinned) + host-spoof reject.")
