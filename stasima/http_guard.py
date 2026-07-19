# SPDX-License-Identifier: Apache-2.0
"""HTTP hardening for the public-exposure era — the funnel gates the hardening audit named.

One ASGI middleware wraps the fleet server's app when the OAuth door is on, applying in order:
  - Host allowlist on the CREDENTIAL routes. The SDK's DNS-rebinding guard covers only /mcp;
    /authorize, /token, /register, /.well-known/* and our /approve were exempt (audit B3).
  - a request-body size cap — a large POST to /approve or /register would otherwise buffer freely
    (audit B5); the tailscale funnel does not cap this, so it must live in-app.
  - per-source rate limiting on the sensitive routes — the TOTP /approve brute-force blocker (the
    load-bearing per-IP throttle; the per-txn burn lives in the provider) and the open-DCR flood
    (audit B1/B2).
  - security headers on every response — CSP/nosniff/no-referrer/HSTS on the credential page
    (audit B8).

Loopback/tailnet-only with no public_url means the OAuth door is off and this never mounts — zero
change to the trial deployment. It arms only when http_public_url turns auth on and the funnel is
the intended perimeter.
"""
import threading
import time
from collections import defaultdict, deque

# per-route (limit, window_seconds), matched by path prefix, most specific first
RATE_RULES = (
    ("/approve", 12, 60),     # TOTP guessing — the brute-force blocker (with the per-txn burn)
    ("/register", 6, 60),     # dynamic client registration flood
    ("/authorize", 30, 60),
    ("/token", 30, 60),
)
MAX_BODY_BYTES = 64 * 1024    # OAuth form/JSON is tiny; anything larger is abuse

SECURITY_HEADERS = [
    (b"content-security-policy", b"default-src 'none'; form-action 'self'; base-uri 'none'"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"strict-transport-security", b"max-age=63072000"),
    (b"x-frame-options", b"DENY"),
]


class RateLimiter:
    """Sliding-window counter per key, in-process, thread-safe. One process serves the whole fleet,
    so an in-memory window is authoritative for this deployment (no cross-node coordination needed)."""

    def __init__(self, limit: int, window_s: float):
        self.limit = limit
        self.window = window_s
        self.hits: dict = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str, now: float) -> bool:
        with self.lock:
            dq = self.hits[key]
            cutoff = now - self.window
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= self.limit:
                return False
            dq.append(now)
            # opportunistic sweep so idle keys don't accumulate in a weeks-long process
            if len(self.hits) > 4096:
                for k in [k for k, d in self.hits.items() if not d or d[-1] < cutoff]:
                    self.hits.pop(k, None)
            return True


class SecurityMiddleware:
    """Pure-ASGI wrapper: Host allowlist + body cap + per-IP rate limit + security headers. Applied
    to the whole app (every route, including the SDK-owned OAuth endpoints), unlike the SDK's
    transport-security which only guards the /mcp session manager."""

    def __init__(self, app, *, allowed_hosts=(), max_body_bytes: int = MAX_BODY_BYTES,
                 rate_rules=RATE_RULES):
        self.app = app
        self.hosts = {h.lower() for h in allowed_hosts if h}
        self.max_body = max_body_bytes
        self.limiters = [(prefix, RateLimiter(lim, win)) for prefix, lim, win in rate_rules]

    async def _reject(self, send, status: int, msg: str):
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"text/plain; charset=utf-8"),
                                *SECURITY_HEADERS]})
        await send({"type": "http.response.body", "body": msg.encode("utf-8")})

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                   for k, v in scope.get("headers", [])}
        path = scope.get("path", "")

        # Host allowlist — covers the credential channel the SDK guard leaves open
        if self.hosts:
            host = headers.get("host", "").rsplit(":", 1)[0].lower()
            if host and host not in self.hosts:
                return await self._reject(send, 421, "host not allowed")

        # body-size cap (Content-Length is what real OAuth/form clients send)
        cl = headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > self.max_body:
            return await self._reject(send, 413, "request entity too large")

        # per-source rate limit on the sensitive routes
        client = scope.get("client")
        ip = client[0] if client else "?"
        now = time.monotonic()
        for prefix, limiter in self.limiters:
            if path.startswith(prefix):
                if not limiter.allow(ip, now):
                    return await self._reject(send, 429, "rate limit exceeded — slow down")
                break

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                # don't duplicate a header the app already set
                have = {k.lower() for k, _ in message["headers"]}
                message["headers"].extend([(k, v) for k, v in SECURITY_HEADERS if k not in have])
            await send(message)

        await self.app(scope, receive, send_with_headers)


def harden(app, *, allowed_hosts=()):
    """Wrap an ASGI app with the hardening middleware. Called from main() when the OAuth door is on."""
    return SecurityMiddleware(app, allowed_hosts=allowed_hosts)
