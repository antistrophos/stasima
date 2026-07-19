# SPDX-License-Identifier: Apache-2.0
"""The OAuth layer — 1.1's door, arrived early (the desktop client demands the MCP authorization
flow from remote connectors before any tool call).

One practitioner, one authenticator: the authorize page approves with the SAME TOTP that gates
canon — no passwords, no accounts, no new secrets. The SDK carries the protocol (discovery, DCR,
PKCE, the token endpoint, bearer middleware); this module is the provider behind it: client and
token STORAGE (revocable state, not truth — auth.sqlite beside the audit log, in the backup path),
the pending-authorization handoff to the approve page, and the TOTP gate with the airlock's own
replay discipline (a consumed window is consumed here too, recorded in the audit ledger).

AS and RS are one server here: the issuer is the same host that serves /mcp.
"""
import json
import os
import secrets as _secrets
import sqlite3
import threading
import time

from mcp.server.auth.provider import (AccessToken, AuthorizationCode, AuthorizationParams,
                                      RefreshToken, TokenError, construct_redirect_uri)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from .airlock import verify_code

CODE_TTL_S = 300          # authorization codes: minutes, single-use
TXN_TTL_S = 600           # pending approvals: the practitioner's walk to the authenticator
ACCESS_TTL_S = 24 * 3600  # a day per access token; the connector refreshes silently
REFRESH_TTL_S = 30 * 24 * 3600
TXN_MISS_CAP = 5          # wrong TOTP codes before a pending approval is burned (brute-force cap)
CLIENT_CAP = 512          # dynamically-registered clients kept before pruning token-less ones


class StasimaOAuth:
    """OAuthAuthorizationServerProvider (structural protocol — no inheritance needed)."""

    def __init__(self, db_path: str, secret_path: str, audit=None):
        self.secret_path = secret_path
        self.audit = audit
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """CREATE TABLE IF NOT EXISTS clients (client_id TEXT PRIMARY KEY, data TEXT);
               CREATE TABLE IF NOT EXISTS codes   (code TEXT PRIMARY KEY, data TEXT, expires_at REAL);
               CREATE TABLE IF NOT EXISTS tokens  (token TEXT PRIMARY KEY, kind TEXT, data TEXT,
                                                   expires_at REAL, paired TEXT);
               CREATE TABLE IF NOT EXISTS txns    (txn TEXT PRIMARY KEY, client_id TEXT, params TEXT,
                                                   created REAL, redirect TEXT)""")
        try:   # per-txn wrong-code counter (the brute-force burn); additive migration
            self.conn.execute("ALTER TABLE txns ADD COLUMN misses INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass   # column already present
        self.conn.commit()
        # pending approvals live in the DB, not memory: the cockpit is a SEPARATE process with the
        # same file, and console approval is the same presence-channel doctrine as landing

    # ---- clients (DCR — the call the desktop makes first) ----
    async def get_client(self, client_id: str):
        with self._lock:
            r = self.conn.execute("SELECT data FROM clients WHERE client_id=?", (client_id,)).fetchone()
        return OAuthClientInformationFull.model_validate_json(r["data"]) if r else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        # DCR is unauthenticated by spec; cap the table so a public flood can't grow auth.sqlite
        # without bound. Prune ABANDONED clients first (no live token references), oldest by
        # insertion — a token-holding connector is never evicted.
        with self._lock:
            n = self.conn.execute("SELECT COUNT(*) c FROM clients").fetchone()["c"]
            if n >= CLIENT_CAP:
                self.conn.execute(
                    "DELETE FROM clients WHERE client_id IN ("
                    "  SELECT client_id FROM clients WHERE client_id NOT IN "
                    "    (SELECT DISTINCT json_extract(data,'$.client_id') FROM tokens) "
                    "  ORDER BY rowid LIMIT ?)", (max(1, n - CLIENT_CAP + 1),))
            self.conn.execute("INSERT OR REPLACE INTO clients VALUES (?,?)",
                              (client_info.client_id, client_info.model_dump_json()))
            self.conn.commit()
        if self.audit is not None:
            self.audit.append("practitioner", "oauth_client_registered",
                              detail={"client_id": client_info.client_id,
                                      "name": client_info.client_name or ""})

    def record_miss(self, txn: str) -> int:
        """A wrong TOTP code on a pending approval: increment its miss counter and BURN the txn once
        the cap is hit (the per-txn half of the brute-force defense; the per-IP throttle is the
        middleware's). Returns remaining attempts (0 = burned)."""
        with self._lock:
            r = self.conn.execute("SELECT misses FROM txns WHERE txn=? AND redirect IS NULL",
                                  (txn,)).fetchone()
            if r is None:
                return 0
            misses = (r["misses"] or 0) + 1
            if misses >= TXN_MISS_CAP:
                self.conn.execute("DELETE FROM txns WHERE txn=?", (txn,))
                self.conn.commit()
                if self.audit is not None:
                    self.audit.append("system", "oauth_txn_burned",
                                      detail={"reason": "too many wrong codes", "misses": misses})
                return 0
            self.conn.execute("UPDATE txns SET misses=? WHERE txn=?", (misses, txn))
            self.conn.commit()
            return TXN_MISS_CAP - misses

    # ---- the authorize handoff (SDK redirects the browser to what we return) ----
    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        now = time.time()
        txn = _secrets.token_urlsafe(16)
        with self._lock:
            self.conn.execute("DELETE FROM txns WHERE created < ? AND redirect IS NULL",
                              (now - TXN_TTL_S,))
            self.conn.execute(
                "INSERT INTO txns (txn, client_id, params, created, redirect, misses) "
                "VALUES (?,?,?,?,NULL,0)",
                (txn, client.client_id, params.model_dump_json(), now))
            self.conn.commit()
        return f"/approve?txn={txn}"

    def pending(self, txn: str):
        """{"client_id", "params", "created", "redirect"} — redirect non-null = already approved
        (by either channel); None = unknown or expired."""
        with self._lock:
            r = self.conn.execute("SELECT client_id, params, created, redirect FROM txns "
                                  "WHERE txn=?", (txn,)).fetchone()
        if r is None or (r["redirect"] is None and time.time() - r["created"] > TXN_TTL_S):
            return None
        return {"client_id": r["client_id"],
                "params": AuthorizationParams.model_validate_json(r["params"]),
                "created": r["created"], "redirect": r["redirect"]}

    def list_pending(self):
        """The cockpit's view: unapproved, unexpired requests, oldest first."""
        cutoff = time.time() - TXN_TTL_S
        with self._lock:
            rows = self.conn.execute(
                "SELECT t.txn, t.client_id, t.created, c.data FROM txns t "
                "LEFT JOIN clients c ON c.client_id = t.client_id "
                "WHERE t.redirect IS NULL AND t.created >= ? ORDER BY t.created", (cutoff,)).fetchall()
        out = []
        for r in rows:
            name = ""
            if r["data"]:
                try:
                    name = OAuthClientInformationFull.model_validate_json(r["data"]).client_name or ""
                except Exception:
                    name = ""
            out.append({"txn": r["txn"], "client_id": r["client_id"], "client_name": name,
                        "age_s": int(time.time() - r["created"])})
        return out

    def totp_window(self, code: str):
        """The airlock's discipline, applied to the door: verify against the SAME secret, and a
        window any purpose has consumed is consumed for this one too (replay refused, on the
        ledger either way)."""
        if not os.path.exists(self.secret_path):
            return None
        with open(self.secret_path, encoding="utf-8") as f:
            secret = f.read().strip()
        w = verify_code(secret, code, time.time())
        if w is None:
            if self.audit is not None:
                self.audit.append("system", "oauth_totp_reject", detail={"reason": "bad code"})
            return None
        if self.audit is not None:
            for e in self.audit.events(op="totp_accept") + self.audit.events(op="oauth_approve"):
                if (e.get("detail") or {}).get("window") == w:
                    self.audit.append("system", "oauth_totp_reject",
                                      detail={"reason": "window already consumed", "window": w})
                    return None
        return w

    def grant(self, txn: str, window: int) -> str:
        """TOTP-channel approval: mint the single-use code, send the browser home."""
        return self._mint(txn, "totp", {"window": window})

    def console_grant(self, txn: str) -> str:
        """Console-channel approval (the cockpit): presence at the terminal IS the gate — the same
        doctrine as landing. No code; the channel rides the audit row instead."""
        return self._mint(txn, "console", {})

    def _mint(self, txn: str, channel: str, extra: dict) -> str:
        with self._lock:
            r = self.conn.execute("SELECT client_id, params, redirect FROM txns WHERE txn=?",
                                  (txn,)).fetchone()
            if r is None:
                raise KeyError("unknown txn")
            if r["redirect"] is not None:
                return r["redirect"]          # already approved by the other channel — idempotent
            params = AuthorizationParams.model_validate_json(r["params"])
            code = _secrets.token_urlsafe(32)
            ac = AuthorizationCode(code=code, scopes=params.scopes or [],
                                   expires_at=time.time() + CODE_TTL_S,
                                   client_id=r["client_id"], code_challenge=params.code_challenge,
                                   redirect_uri=params.redirect_uri,
                                   redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
                                   resource=params.resource, subject="practitioner")
            redirect = construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)
            self.conn.execute("INSERT INTO codes VALUES (?,?,?)",
                              (code, ac.model_dump_json(), ac.expires_at))
            self.conn.execute("UPDATE txns SET redirect=? WHERE txn=?", (redirect, txn))
            self.conn.commit()
        if self.audit is not None:
            self.audit.append("practitioner", "oauth_approve",
                              detail={"client_id": r["client_id"], "channel": channel, **extra})
        return redirect

    # ---- codes -> tokens (PKCE verified by the SDK's token handler before exchange) ----
    async def load_authorization_code(self, client, authorization_code: str):
        with self._lock:
            r = self.conn.execute("SELECT data, expires_at FROM codes WHERE code=?",
                                  (authorization_code,)).fetchone()
        if r is None or r["expires_at"] < time.time():
            return None
        ac = AuthorizationCode.model_validate_json(r["data"])
        return ac if ac.client_id == client.client_id else None

    def _mint_pair(self, client_id: str, scopes: list, subject) -> OAuthToken:
        now = time.time()
        at = AccessToken(token=_secrets.token_urlsafe(32), client_id=client_id, scopes=scopes,
                         expires_at=int(now + ACCESS_TTL_S), subject=subject)
        rt = RefreshToken(token=_secrets.token_urlsafe(32), client_id=client_id, scopes=scopes,
                          expires_at=int(now + REFRESH_TTL_S), subject=subject)
        with self._lock:
            self.conn.execute("INSERT INTO tokens VALUES (?,?,?,?,?)",
                              (at.token, "access", at.model_dump_json(), float(at.expires_at), rt.token))
            self.conn.execute("INSERT INTO tokens VALUES (?,?,?,?,?)",
                              (rt.token, "refresh", rt.model_dump_json(), float(rt.expires_at), at.token))
            self.conn.commit()
        return OAuthToken(access_token=at.token, expires_in=ACCESS_TTL_S,
                          scope=" ".join(scopes) if scopes else None, refresh_token=rt.token)

    async def exchange_authorization_code(self, client, authorization_code: AuthorizationCode) -> OAuthToken:
        with self._lock:
            self.conn.execute("DELETE FROM codes WHERE code=?", (authorization_code.code,))
            self.conn.commit()
        return self._mint_pair(client.client_id, authorization_code.scopes, authorization_code.subject)

    # ---- refresh (rotate the whole pair) ----
    async def load_refresh_token(self, client, refresh_token: str):
        with self._lock:
            r = self.conn.execute("SELECT data, expires_at FROM tokens WHERE token=? AND kind='refresh'",
                                  (refresh_token,)).fetchone()
        if r is None or r["expires_at"] < time.time():
            return None
        rt = RefreshToken.model_validate_json(r["data"])
        return rt if rt.client_id == client.client_id else None

    async def exchange_refresh_token(self, client, refresh_token: RefreshToken, scopes: list) -> OAuthToken:
        await self.revoke_token(refresh_token)
        return self._mint_pair(client.client_id, scopes or refresh_token.scopes, refresh_token.subject)

    # ---- verification (every /mcp request rides this via the bearer middleware) ----
    async def load_access_token(self, token: str):
        with self._lock:
            r = self.conn.execute("SELECT data, expires_at FROM tokens WHERE token=? AND kind='access'",
                                  (token,)).fetchone()
        if r is None or r["expires_at"] < time.time():
            return None
        return AccessToken.model_validate_json(r["data"])

    async def revoke_token(self, token) -> None:
        with self._lock:
            r = self.conn.execute("SELECT paired FROM tokens WHERE token=?", (token.token,)).fetchone()
            self.conn.execute("DELETE FROM tokens WHERE token=?", (token.token,))
            if r and r["paired"]:
                self.conn.execute("DELETE FROM tokens WHERE token=?", (r["paired"],))
            self.conn.commit()


def approve_page(txn: str, error: str = "") -> str:
    err = f'<p style="color:#b00">{error}</p>' if error else ""
    refresh = "" if error else f'<meta http-equiv="refresh" content="2;url=/approve?txn={txn}">'
    return f"""<!doctype html><meta name="viewport" content="width=device-width, initial-scale=1">
{refresh}<title>Stasima — approve connector</title>
<body style="font-family:system-ui;max-width:26rem;margin:4rem auto;padding:0 1rem">
<h2>Approve this connector?</h2>
<p>A client is requesting access to the Stasima server. Enter a code from the practitioner's
authenticator — the same one that gates canon — <b>or approve from the cockpit</b> (HTTP service
screen; this page follows on its own). If you did not initiate this, close the page.</p>
{err}
<form method="post" action="/approve">
<input type="hidden" name="txn" value="{txn}">
<input name="code" inputmode="numeric" autocomplete="one-time-code" autofocus
       placeholder="123456" style="font-size:1.4rem;width:8rem;text-align:center">
<button style="font-size:1.1rem;margin-left:.6rem">Approve</button>
</form></body>"""
