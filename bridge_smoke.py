# SPDX-License-Identifier: Apache-2.0
"""
The bridge smoke — the pre-cutover check, run on the deploying machine, NOT part of the suite:
drive the ported server through the REAL `mcp-proxy` bridge (the desktop client's connector, a
handshake-era 1.x client living in a different interpreter), in both http modes, and report
whether an open bridge survives a service restart in each.

    .venv\\Scripts\\python.exe bridge_smoke.py            (STASIMA_BRIDGE_PYTHON overrides the bridge's interpreter)

What it proves: (1) the v2 server serves the bridge's protocol — tools list, announce, a write —
exactly as the fleet uses it today; (2) whether `http_stateless = true` earns its keep: with
sessions, a bridge holds one upstream session and a restarted service no longer knows it (the
restart rule in OPERATIONS); without sessions every request stands alone, so a restart should be
invisible to an open bridge. The script reports what it sees; it rules nothing.
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
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

BRIDGE_PY = os.environ.get("STASIMA_BRIDGE_PYTHON",
                           r"C:\Users\eel\AppData\Local\Python\pythoncore-3.14-64\python.exe")
if not os.path.exists(BRIDGE_PY) or sp.run([BRIDGE_PY, "-c", "import mcp_proxy"], capture_output=True).returncode:
    print(f"SKIP -- no mcp_proxy in {BRIDGE_PY} (set STASIMA_BRIDGE_PYTHON to the bridge's interpreter)")
    sys.exit(0)
bridge_mcp = sp.run([BRIDGE_PY, "-c", "import importlib.metadata as m; print(m.version('mcp'), m.version('mcp-proxy'))"],
                    capture_output=True, text=True).stdout.strip()
print(f"bridge interpreter  {BRIDGE_PY}\nbridge packages     mcp {bridge_mcp.split()[0]} / mcp-proxy {bridge_mcp.split()[1]}")
print(f"server interpreter  {sys.executable}")


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def boot(cfgpath, port):
    proc = sp.Popen([sys.executable, "-m", "stasima.cap_server"], cwd=HERE,
                    env=dict(os.environ, STASIMA_CONFIG=cfgpath), stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close(); return proc
        except OSError:
            if proc.poll() is not None:
                raise SystemExit(f"server exited early ({proc.returncode})")
            time.sleep(0.3)
    raise SystemExit("server never opened the port")


def stop(proc):
    proc.terminate(); proc.wait(timeout=10)
    time.sleep(0.5)   # let the port free


def text(res):
    return "".join(getattr(c, "text", "") for c in res.content)


async def drive(mode, cfgpath, port):
    url = f"http://127.0.0.1:{port}/mcp"
    params = StdioServerParameters(command=BRIDGE_PY, args=["-m", "mcp_proxy", "--transport", "streamablehttp", url])
    proc = boot(cfgpath, port)
    survived = None
    try:
        async with Client(params) as c:            # the bridge speaks stdio to us, 1.x streamable HTTP to the server
            tools = sorted(t.name for t in (await c.list_tools()).tools)
            a = await c.call_tool("announce", {"instance_id": "bridge-probe"})
            ok_arrive = "Welcome" in text(a)
            w = await c.call_tool("kip_commit", {"instance_id": "bridge-probe", "domain": "state",
                                                 "slug": "b1", "body": "over the bridge", "op_id": "bb1"})
            ok_write = not w.is_error
            # the restart: service down and up on the SAME port while the bridge stays open
            stop(proc)
            proc = boot(cfgpath, port)
            try:
                with anyio.fail_after(20):
                    r = await c.call_tool("canon_state", {})
                survived = not r.is_error
                why = "" if survived else text(r)[:120]
            except Exception as e:                  # the bridge's dead upstream session surfaces here
                survived, why = False, f"{type(e).__name__}: {str(e)[:120]}"
    except Exception as e:
        print(f"{mode:<10} FAILED before the restart: {type(e).__name__}: {str(e)[:200]}")
        stop(proc)
        return
    finally:
        if proc.poll() is None:
            stop(proc)
    print(f"{mode:<10} tools={len(tools)} announce={'OK' if ok_arrive else 'FAIL'} write={'OK' if ok_write else 'FAIL'} "
          f"survives-restart={'YES' if survived else 'NO'}{(' (' + why + ')') if why else ''}")


for mode, extra in (("sessions", ""), ("stateless", "http_stateless = true\n")):
    work = tempfile.mkdtemp(prefix=f"stasima-bridge-{mode}-")
    gd = os.path.join(work, "stasima.git")
    sp.run(["git", "init", "--bare", "-q", gd], check=True)
    port = free_port()
    cfgpath = os.path.join(work, "stasima.toml")
    with open(cfgpath, "w", encoding="utf-8") as f:
        f.write(f'git_dir = "{gd.replace(os.sep, "/")}"\ntransport = "http"\nhttp_port = {port}\n'
                f'binding_mode = "off"\n{extra}')
    anyio.run(drive, mode, cfgpath, port)

print("\ndone -- read the two rows; the cutover section in OPERATIONS says what each answer means.")
