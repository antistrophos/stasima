# SPDX-License-Identifier: Apache-2.0
"""
The OAuth door, end to end against a LIVE http server:
  1. discovery: protected-resource + AS metadata are served, DCR is advertised
  2. the /mcp endpoint is protected — no bearer -> 401 with a WWW-Authenticate pointer
  3. register (DCR) -> authorize -> the approve page -> WRONG code refused -> the RIGHT TOTP
     redirects with a code -> PKCE exchange -> a bearer that calls a tool
  4. the TOTP replay guard: the just-used window cannot approve a second connector
  5. no-auth mode (no public_url) still serves /mcp openly — the loopback-trust regression guard
"""
import base64
import hashlib
import json
import os
import re
import secrets
import socket
import subprocess as sp
import sys
import tempfile
import time
import urllib.parse

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from stasima.airlock import generate_secret, totp_at
from stasima.http_guard import RateLimiter

# ---- unit: the sliding-window rate limiter (deterministic clock) ----
rl = RateLimiter(limit=3, window_s=10)
assert all(rl.allow("ip-a", t) for t in (0.0, 1.0, 2.0)), "first 3 within window allowed"
assert not rl.allow("ip-a", 3.0), "4th within window denied"
assert rl.allow("ip-b", 3.0), "a different key is independent"
assert rl.allow("ip-a", 11.0), "the window slid — oldest hit aged out, allowed again"
print("0. rate limiter      OK (window fills, denies, slides; keys independent)")


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return p


def boot(cfg_text):
    work = tempfile.mkdtemp(prefix="stasima-oauth-")
    gd = os.path.join(work, "stasima.git")
    sp.run(["git", "init", "--bare", "-q", gd], check=True)
    port = free_port()
    cfgpath = os.path.join(work, "stasima.toml")
    with open(cfgpath, "w", encoding="utf-8") as f:
        f.write(f'git_dir = "{gd.replace(os.sep, "/")}"\ntransport = "http"\nhttp_port = {port}\n' + cfg_text)
    proc = sp.Popen([sys.executable, "-m", "stasima.cap_server"],
                    env=dict(os.environ, STASIMA_CONFIG=cfgpath), cwd=HERE,
                    stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            break
        except OSError:
            if proc.poll() is not None:
                raise SystemExit(f"server exited early ({proc.returncode})")
            time.sleep(0.3)
    else:
        raise SystemExit("server never opened the port")
    return work, port, proc


# ---- auth ON: provision a TOTP secret, point public_url at loopback ----
work, port, proc = None, None, None
try:
    base = f"http://127.0.0.1:{free_port()}"   # placeholder; replaced below with the real port
    w2 = tempfile.mkdtemp(prefix="stasima-oauth-")
    gd = os.path.join(w2, "stasima.git")
    sp.run(["git", "init", "--bare", "-q", gd], check=True)
    port = free_port()
    public = f"http://127.0.0.1:{port}"
    secret = generate_secret()
    with open(os.path.join(w2, "totp.secret"), "w", encoding="utf-8") as f:
        f.write(secret)
    cfgpath = os.path.join(w2, "stasima.toml")
    with open(cfgpath, "w", encoding="utf-8") as f:
        f.write(f'git_dir = "{gd.replace(os.sep, "/")}"\ntransport = "http"\nhttp_port = {port}\n'
                f'http_public_url = "{public}"\nhttp_allowed_hosts = ["127.0.0.1"]\n')
    proc = sp.Popen([sys.executable, "-m", "stasima.cap_server"],
                    env=dict(os.environ, STASIMA_CONFIG=cfgpath), cwd=HERE,
                    stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close(); break
        except OSError:
            if proc.poll() is not None:
                raise SystemExit(f"server exited early ({proc.returncode})")
            time.sleep(0.3)

    c = httpx.Client(base_url=public, timeout=15)

    # 1. discovery — protected-resource metadata is resource-path-suffixed (RFC 9728 §3.1)
    prm = c.get("/.well-known/oauth-protected-resource/mcp").json()
    assert "authorization_servers" in prm, prm
    asm = c.get("/.well-known/oauth-authorization-server").json()
    for k in ("registration_endpoint", "authorization_endpoint", "token_endpoint"):
        assert k in asm, (k, asm)
    print("1. discovery         OK (protected-resource + AS metadata + DCR advertised)")

    # 2. /mcp requires a bearer
    r = c.post("/mcp", json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
               headers={"Accept": "application/json, text/event-stream"})
    assert r.status_code == 401, r.status_code
    assert "WWW-Authenticate" in r.headers, dict(r.headers)
    print("2. /mcp protected    OK (401 + WWW-Authenticate before any token)")

    # 3. register -> authorize -> approve (wrong then right) -> exchange -> authed call
    reg = c.post(asm["registration_endpoint"],
                 json={"client_name": "test-connector", "redirect_uris": ["http://127.0.0.1:9/cb"],
                       "grant_types": ["authorization_code", "refresh_token"],
                       "response_types": ["code"], "token_endpoint_auth_method": "none"}).json()
    cid = reg["client_id"]
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    auth = c.get(asm["authorization_endpoint"], params={
        "response_type": "code", "client_id": cid, "redirect_uri": "http://127.0.0.1:9/cb",
        "code_challenge": challenge, "code_challenge_method": "S256", "state": "xyz"})
    # the SDK redirects to /approve?txn=...; follow to the page, scrape the txn
    loc = auth.headers.get("location", "")
    assert "/approve" in loc, (auth.status_code, loc)
    txn = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query)["txn"][0]
    page = c.get("/approve", params={"txn": txn})
    assert "Approve this connector" in page.text, page.text[:200]

    bad = c.post("/approve", data={"txn": txn, "code": "000000"})
    assert bad.status_code == 401 and "refused" in bad.text, (bad.status_code, bad.text[:120])

    good = c.post("/approve", data={"txn": txn, "code": totp_at(secret, int(time.time() // 30))},
                  follow_redirects=False)
    assert good.status_code == 302, (good.status_code, good.text[:120])
    code = urllib.parse.parse_qs(urllib.parse.urlparse(good.headers["location"]).query)["code"][0]

    tok = c.post(asm["token_endpoint"], data={
        "grant_type": "authorization_code", "code": code, "client_id": cid,
        "redirect_uri": "http://127.0.0.1:9/cb", "code_verifier": verifier}).json()
    assert tok.get("access_token") and tok.get("refresh_token"), tok
    print("3. register→approve→exchange OK (wrong code refused; TOTP redirects; PKCE mints a bearer)")

    hdr = {"Authorization": f"Bearer {tok['access_token']}",
           "Accept": "application/json, text/event-stream"}

    def sse_json(resp):   # streamable-http replies are SSE: pull the data: line's JSON
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        return json.loads(resp.text)

    init = c.post("/mcp", headers=hdr, json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "oauth-test", "version": "1"}}})
    assert init.status_code == 200, (init.status_code, init.text[:160])   # bearer passed auth
    sid = init.headers["mcp-session-id"]
    sh = {**hdr, "mcp-session-id": sid}
    c.post("/mcp", headers=sh, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    call = c.post("/mcp", headers=sh, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert call.status_code == 200 and "announce" in call.text, (call.status_code, call.text[:200])
    print("   bearer calls tools OK (the token opens /mcp; initialize→tools/list over the session)")

    # 4. replay: the SAME window cannot approve a second connector
    verifier2 = secrets.token_urlsafe(48)
    challenge2 = base64.urlsafe_b64encode(hashlib.sha256(verifier2.encode()).digest()).decode().rstrip("=")
    auth2 = c.get(asm["authorization_endpoint"], params={
        "response_type": "code", "client_id": cid, "redirect_uri": "http://127.0.0.1:9/cb",
        "code_challenge": challenge2, "code_challenge_method": "S256", "state": "z2"})
    txn2 = urllib.parse.parse_qs(urllib.parse.urlparse(auth2.headers["location"]).query)["txn"][0]
    replay = c.post("/approve", data={"txn": txn2, "code": totp_at(secret, int(time.time() // 30))})
    assert replay.status_code == 401, "a consumed TOTP window must not approve twice: " + str(replay.status_code)
    print("4. TOTP replay guard OK (a consumed window is refused a second time)")

    # 5. the CONSOLE channel: a separate process (the cockpit) approves the still-pending txn2
    # through the shared auth store — no code; presence is the gate — and the browser's polling
    # page follows home on its next GET
    from stasima.oauth import StasimaOAuth
    cockpit = StasimaOAuth(os.path.join(w2, "auth.sqlite"), os.path.join(w2, "totp.secret"))
    pend = cockpit.list_pending()
    assert any(p["txn"] == txn2 for p in pend), pend
    cockpit.console_grant(txn2)
    followed = c.get("/approve", params={"txn": txn2}, follow_redirects=False)
    assert followed.status_code == 302 and "code=" in followed.headers["location"], \
        (followed.status_code, followed.headers.get("location", ""))
    code2 = urllib.parse.parse_qs(urllib.parse.urlparse(followed.headers["location"]).query)["code"][0]
    tok2 = c.post(asm["token_endpoint"], data={
        "grant_type": "authorization_code", "code": code2, "client_id": cid,
        "redirect_uri": "http://127.0.0.1:9/cb", "code_verifier": verifier2}).json()
    assert tok2.get("access_token"), tok2
    print("5. console channel   OK (cockpit approves cross-process; the polling page follows; PKCE still exchanges)")

    # 6. brute-force burn: a fresh txn tolerates a few wrong codes, then CLOSES (429) — the per-txn
    # half of the defense (the per-IP throttle is the middleware, unit-tested above)
    verifier3 = secrets.token_urlsafe(48)
    challenge3 = base64.urlsafe_b64encode(hashlib.sha256(verifier3.encode()).digest()).decode().rstrip("=")
    auth3 = c.get(asm["authorization_endpoint"], params={
        "response_type": "code", "client_id": cid, "redirect_uri": "http://127.0.0.1:9/cb",
        "code_challenge": challenge3, "code_challenge_method": "S256", "state": "z3"})
    txn3 = urllib.parse.parse_qs(urllib.parse.urlparse(auth3.headers["location"]).query)["txn"][0]
    codes_seen = [c.post("/approve", data={"txn": txn3, "code": "000000"}).status_code for _ in range(5)]
    assert codes_seen[:4] == [401, 401, 401, 401], codes_seen
    assert codes_seen[4] == 429, ("txn must burn after the miss cap", codes_seen)
    assert c.get("/approve", params={"txn": txn3}).status_code == 400, "burned txn is gone"
    print("6. brute-force burn  OK (wrong codes tolerated then the txn is burned at the cap)")

    # 7. hardening middleware: bad Host rejected app-wide (not just /mcp); oversized body rejected
    badhost = c.post("/register", headers={"Host": "evil.example.com"},
                     json={"client_name": "x", "redirect_uris": ["http://127.0.0.1:9/cb"]})
    assert badhost.status_code == 421, ("Host allowlist must cover the credential routes", badhost.status_code)
    toobig = c.post("/register", content=b"x" * (128 * 1024),
                    headers={"Content-Type": "application/json"})
    assert toobig.status_code == 413, ("body cap must reject oversized POST", toobig.status_code)
    hdrs = c.get("/.well-known/oauth-authorization-server").headers
    assert "content-security-policy" in hdrs and hdrs.get("x-content-type-options") == "nosniff", dict(hdrs)
    print("7. hardening mw      OK (bad Host 421, oversized 413, security headers present)")
    c.close()
finally:
    if proc is not None:
        proc.terminate(); proc.wait(timeout=10)

# 8. no-auth mode still opens /mcp (the regression guard)
w3, p3, proc3 = boot("")
try:
    r = httpx.post(f"http://127.0.0.1:{p3}/mcp",
                   headers={"Accept": "application/json, text/event-stream"},
                   json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                    "clientInfo": {"name": "t", "version": "1"}}}, timeout=15)
    assert r.status_code == 200, (r.status_code, r.text[:160])
    print("8. no-auth mode      OK (/mcp open when http_public_url is unset — loopback trust intact)")
finally:
    proc3.terminate(); proc3.wait(timeout=10)

print("\nOK -- oauth: discovery, protected endpoint, DCR→approve→PKCE→bearer, replay guard, no-auth regression.")
