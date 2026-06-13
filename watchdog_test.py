# SPDX-License-Identifier: Apache-2.0
"""
Parent-death self-reap. The stdio server already exits on stdin EOF (clean disconnect); this guards
the OTHER path — a client that dies WITHOUT closing the pipe must not leave an orphan. A helper
spawns the server, we kill the HELPER (the server's parent), and the server must exit on its own.
"""
import os
import subprocess as sp
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


work = tempfile.mkdtemp(prefix="stasima-wd-")
gd = os.path.join(work, "stasima.git")
sp.run(["git", "init", "--bare", "-q", gd], check=True)
cfg = os.path.join(work, "stasima.toml")
with open(cfg, "w", encoding="utf-8") as f:
    f.write(f'git_dir = "{gd.replace(os.sep, "/")}"\ntransport = "stdio"\n')

# a helper that spawns the server as ITS child, prints the server PID, then idles (the "client")
helper_src = f"""
import subprocess, sys, time, os
p = subprocess.Popen([sys.executable, "-m", "stasima.cap_server"],
                     stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     env=dict(os.environ, STASIMA_CONFIG={cfg!r}, PYTHONPATH={HERE!r}))
print(p.pid, flush=True)
time.sleep(120)
"""
helper = sp.Popen([sys.executable, "-c", helper_src], stdout=sp.PIPE, text=True)
server_pid = int(helper.stdout.readline().strip())
time.sleep(2)
assert alive(server_pid), "server should be running while its parent (the helper) is alive"
print(f"  server {server_pid} up under helper {helper.pid}")

# the client dies WITHOUT closing the server's stdin (force-kill the helper)
helper.kill()
helper.wait(timeout=10)
print("  killed the parent (helper) — watching the server self-reap")

for i in range(15):
    time.sleep(1)
    if not alive(server_pid):
        print(f"  --> server reaped itself ~{i + 1}s after the parent died. No orphan.")
        break
else:
    try:
        os.kill(server_pid, 9)
    except Exception:
        pass
    raise SystemExit("FAIL: server outlived its dead parent — orphan watchdog did not fire")

print("OK -- parent-death watchdog: stdio server self-reaps when its client vanishes.")
