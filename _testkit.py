# SPDX-License-Identifier: Apache-2.0
"""The suite's shared helpers — the pieces every *_test.py used to carry its own copy of.

Deliberately tiny and dependency-free beyond the suite's own imports: a fresh bare repo, the
result-payload reader, the refusal readers, and the free-port / wait-for-port pair the transport
tests use. Tests stay standalone scripts (run one with `python <name>_test.py`); they import this
by name from their own directory. Not a test itself (the runner globs *_test.py; this is _testkit).
"""
import json
import os
import socket
import subprocess
import tempfile
import time


def fresh_repo(prefix: str):
    """A scratch working dir with a fresh bare repository inside: (work, git_dir)."""
    work = tempfile.mkdtemp(prefix=prefix)
    gd = os.path.join(work, "stasima.git")
    subprocess.run(["git", "init", "--bare", "-q", gd], check=True)
    return work, gd


def text(res) -> str:
    """The text content of a tool result, joined (a refusal's sentence; a plain reply)."""
    return "".join(getattr(c, "text", "") for c in res.content)


def payload(res):
    """A tool result's payload: the structured content if the SDK sent it (unwrapping the
    `{"result": x}` envelope it uses for scalars and lists), else the text parsed as JSON, else the
    raw text. One reader for every shape the 29 tools return."""
    sc = res.structured_content
    if sc is not None:
        if isinstance(sc, dict) and set(sc.keys()) == {"result"}:
            return sc["result"]
        return sc
    txt = text(res)
    try:
        return json.loads(txt)
    except Exception:
        return txt


def is_err(res) -> bool:
    return bool(res.is_error)


def err_text(res) -> str:
    """The refusal as the seat reads it (same as text(); named for what the assertion means)."""
    return text(res)


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_port(port: int, proc=None, timeout: float = 30.0) -> None:
    """Block until 127.0.0.1:port accepts a connection; raise SystemExit if `proc` exits first
    or the deadline passes."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            return
        except OSError:
            if proc is not None and proc.poll() is not None:
                raise SystemExit(f"server exited early ({proc.returncode})")
            time.sleep(0.3)
    raise SystemExit("server never opened the port")
