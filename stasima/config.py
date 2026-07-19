# SPDX-License-Identifier: Apache-2.0
"""
Configuration — one typed, validated config per deployment, replacing scattered env vars.

Loads from a TOML file (flat keys) with env-var overrides; sensible defaults fill the rest. Pure
stdlib (`tomllib`), no component imports — the assembly from a Config lives in cap_server
(`server_from_config`), the single place wiring happens. GitHub creds + notification endpoints
arrive with 1.1 (multi-user / sync); they're intentionally absent here.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields


class ConfigError(Exception):
    pass


# env var -> field name (env overrides the file; both override defaults)
_ENV = {
    "STASIMA_GIT_DIR": "git_dir",
    "STASIMA_APPROVERS": "approvers",
    "STASIMA_CANON_REF": "canon_ref",
    "STASIMA_MAP_DB": "map_db",
    "STASIMA_AUDIT_DB": "audit_db",
    "STASIMA_EMBED_URL": "embed_url",
    "STASIMA_EMBED_MODEL": "embed_model",
    "STASIMA_EMBED_DIM": "embed_dim",
}


@dataclass
class Config:
    git_dir: str = ""
    deployment_name: str = ""   # this deployment's own name (practice-side); blank = generic "Stasima"
    approvers: list = field(default_factory=lambda: ["practitioner"])
    canon_ref: str = "refs/heads/main"
    map_db: str = ""        # blank -> derived beside git_dir (throwaway cache)
    audit_db: str = ""      # blank -> derived beside git_dir (TRUTH — back it up)
    committer_name: str = "capstore"
    committer_email: str = "capstore@stasima.local"
    embed_backend: str = "stub"            # "stub" | "local-server"
    embed_url: str = ""
    embed_model: str = "nomic-embed-text"
    embed_dim: int = 768
    # task prefixes — defaults match the default model (nomic is prefix-conditioned and degrades
    # badly without them). CLEAR these if you switch to a model that doesn't use prefixes.
    embed_doc_prefix: str = "search_document: "
    embed_query_prefix: str = "search_query: "
    orientation_base: str = "technical/orientation"
    # state-sequence origin: canon's seq before any land (first land = origin + 1). The suite
    # default is the original practice's chat-era freeze (::3B); a fresh deployment may set 0
    # (TOML accepts hex: seq_origin = 0x3b).
    seq_origin: int = 0x3B
    # airlock (TOTP two-phase remote approval). Floor must exceed worst-case code lifetime
    # (30s step + ±1 window ≈ 90s) so no code obtained at staging survives to landing.
    airlock_secret_path: str = ""   # blank -> derived beside git_dir; NOT in git
    # the OAuth door (HTTP era): setting the PUBLIC url (the TLS name clients dial, e.g. the
    # tailnet https://host.tailXXXX.ts.net) turns the authorization server ON — discovery, DCR,
    # PKCE, TOTP-approved tokens; /mcp then requires a bearer. Blank = no auth (loopback trust).
    http_public_url: str = ""
    airlock_floor_s: int = 120
    airlock_ceiling_s: int = 7200
    # transport: "stdio" (default — each client spawns the server) or "http" (one continuously-
    # running server; clients connect to http://<host>:<port>/mcp). Until transport auth exists
    # (1.1), http binds are restricted to loopback or the Tailscale CGNAT range — the tailnet
    # slots in via `tailscale serve` proxying to loopback; nothing listens toward the open internet.
    transport: str = "stdio"
    http_host: str = "127.0.0.1"
    http_port: int = 8787
    # extra Host values the http transport accepts (DNS-rebinding protection allows the bind
    # address + localhost automatically). Needed when a proxy forwards with its own Host —
    # e.g. tailscale serve: http_allowed_hosts = ["yourbox.your-tailnet.ts.net"]
    http_allowed_hosts: list = field(default_factory=list)
    # Per-git-op timeout (seconds). A local git op on a text corpus is sub-second; a hang means
    # contention (e.g. a second server process on the repo). 0 = auto by transport: 2s for stdio
    # (one client, no queuing) / 20s for http (concurrent clients can briefly queue). Raise it if a
    # land/reindex on a very large corpus legitimately approaches the limit.
    git_timeout: float = 0.0
    # Timeout (seconds) for NETWORK/batch git ops — push/fetch/ls-remote, i.e. backup, mirror, sync.
    # These legitimately take seconds-to-minutes (slow hardware, slow link, large transfer), so they
    # are NOT bound by the tight steady-state git_timeout above. Raise it for a huge corpus over a slow
    # link; lower it to fail a stuck remote faster.
    git_network_timeout: float = 300.0
    # Relevance floor for map_search: hits below it are withheld (a count reports them). None = the
    # embedder's own calibrated default (stub: 0.0 = off — its scores don't separate true from junk).
    # Set only after measuring where YOUR model's true/junk scores separate on YOUR corpus.
    search_score_floor: float | None = None

    @classmethod
    def load(cls, path: str | None = None, env: dict | None = None) -> "Config":
        env = os.environ if env is None else env
        data: dict = {}
        if path:
            if not os.path.exists(path):
                raise ConfigError(f"config file not found: {path}")
            with open(path, "rb") as f:
                data.update(tomllib.load(f))
        for ev, name in _ENV.items():
            if env.get(ev):
                data[name] = env[ev]
        if env.get("STASIMA_EMBED_URL") and "embed_backend" not in data:
            data["embed_backend"] = "local-server"
        if isinstance(data.get("approvers"), str):
            data["approvers"] = [a.strip() for a in data["approvers"].split(",") if a.strip()]
        for intf in ("embed_dim", "airlock_floor_s", "airlock_ceiling_s", "seq_origin", "http_port"):
            if intf in data:
                try:
                    data[intf] = int(data[intf])
                except (TypeError, ValueError):
                    raise ConfigError(f"{intf} must be an integer, got {data[intf]!r}")
        for _fl in ("git_timeout", "git_network_timeout", "search_score_floor"):
            if _fl in data and data[_fl] is not None:
                try:
                    data[_fl] = float(data[_fl])
                except (TypeError, ValueError):
                    raise ConfigError(f"{_fl} must be a number, got {data[_fl]!r}")
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ConfigError(f"unknown config keys: {sorted(unknown)} (config is flat TOML; check spelling)")
        cfg = cls(**{k: v for k, v in data.items() if k in known})
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if not self.git_dir:
            raise ConfigError("git_dir is required (set it in the config file or STASIMA_GIT_DIR)")
        if self.embed_backend not in ("stub", "local-server"):
            raise ConfigError(f"embed_backend must be 'stub' or 'local-server', got {self.embed_backend!r}")
        if self.embed_backend == "local-server" and not self.embed_url:
            raise ConfigError("embed_backend 'local-server' requires embed_url")
        if int(self.embed_dim) <= 0:
            raise ConfigError("embed_dim must be a positive integer")
        if not self.approvers:
            raise ConfigError("at least one approver is required")
        if self.airlock_floor_s <= 0 or self.airlock_ceiling_s <= self.airlock_floor_s:
            raise ConfigError("airlock gates must satisfy 0 < airlock_floor_s < airlock_ceiling_s")
        if self.transport not in ("stdio", "http"):
            raise ConfigError(f"transport must be 'stdio' or 'http', got {self.transport!r}")
        if self.transport == "http":
            if not (0 < self.http_port < 65536):
                raise ConfigError("http_port must be 1-65535")
            self._check_bind_address(self.http_host)
        if self.http_public_url:
            # the OAuth door's public identity: only meaningful under http, must be a real URL, and
            # https unless it's a loopback dev endpoint (a TLS terminator — tailscale serve/funnel —
            # fronts a real deployment). Reconcile it into the Host allowlist so the hardening
            # middleware accepts the proxied Host it will arrive under.
            if self.transport != "http":
                raise ConfigError("http_public_url is only meaningful with transport='http' — it "
                                  "turns the OAuth authorization server on; remove it or switch transport")
            from urllib.parse import urlparse
            u = urlparse(self.http_public_url)
            if u.scheme not in ("http", "https") or not u.hostname:
                raise ConfigError(f"http_public_url must be a full URL (e.g. "
                                  f"https://host.tailXXXX.ts.net), got {self.http_public_url!r}")
            loopback = u.hostname in ("127.0.0.1", "::1", "localhost")
            if u.scheme != "https" and not loopback:
                raise ConfigError(f"http_public_url must be https for a non-loopback host "
                                  f"({u.hostname!r}) — the connector rides TLS; got scheme {u.scheme!r}")
            if u.hostname not in self.http_allowed_hosts:
                self.http_allowed_hosts = list(self.http_allowed_hosts) + [u.hostname]
        if self.git_timeout < 0:
            raise ConfigError("git_timeout must be >= 0 (0 = auto by transport: 2s stdio / 20s http)")
        if self.git_network_timeout <= 0:
            raise ConfigError("git_network_timeout must be > 0 (seconds; the bound for backup/mirror/sync git ops)")

    def resolved_git_timeout(self) -> float:
        if self.git_timeout > 0:
            return self.git_timeout
        return 2.0 if self.transport == "stdio" else 20.0

    @staticmethod
    def _check_bind_address(host: str) -> None:
        """Defense-in-depth on the LISTEN address: the process binds only loopback or a Tailscale
        tailnet address (CGNAT 100.64.0.0/10). Public reach is via a TLS terminator (tailscale
        serve/funnel) proxying to loopback, and the OAuth door (http_public_url) is the auth
        perimeter — this bind restriction sits behind it, not instead of it."""
        import ipaddress
        if host == "localhost":
            return
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            raise ConfigError(f"http_host must be an IP address or 'localhost', got {host!r}")
        if ip.is_loopback or ip in ipaddress.ip_network("100.64.0.0/10"):
            return
        raise ConfigError(
            f"http_host {host!r} would listen beyond loopback/tailnet. Bind 127.0.0.1 and expose it "
            f"with `tailscale serve` (auth via the OAuth door, http_public_url), or bind your "
            f"machine's Tailscale 100.x address directly. A wider raw bind is not supported.")

    def resolved_map_db(self) -> str:
        return self.map_db or os.path.join(os.path.dirname(self.git_dir), "map_index.sqlite")

    def resolved_audit_db(self) -> str:
        return self.audit_db or os.path.join(os.path.dirname(self.git_dir), "audit.sqlite")

    def resolved_auth_db(self) -> str:
        """The OAuth store, beside the audit log — one home for the derived path (was open-coded in
        the server and the cockpit; drift there is a silent console-approval outage)."""
        return os.path.join(os.path.dirname(self.resolved_audit_db()), "auth.sqlite")

    def resolved_airlock_secret(self) -> str:
        return self.airlock_secret_path or os.path.join(os.path.dirname(self.git_dir), "totp.secret")
