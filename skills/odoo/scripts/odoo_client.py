"""Odoo external API client (JSON-RPC over /jsonrpc). Stdlib only, Python 3.10+.

Works with Odoo 8 to 18 and with 19 while /jsonrpc is still served. The API key goes in
the password slot. Credentials come from env or ~/.config/odoo/<profile> (KEY=VALUE).
"""
from __future__ import annotations

import itertools
import json
import os
import stat
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("ODOO_CONFIG_DIR", Path.home() / ".config" / "odoo"))
KEYS = ("ODOO_URL", "ODOO_DB", "ODOO_USER", "ODOO_API_KEY")

# Methods that never change data. Anything else through `call` needs --yes.
READ_METHODS = {
    "search", "search_read", "read", "search_count", "fields_get", "read_group",
    "name_search", "name_get", "check_access_rights", "default_get", "get_views",
    "fields_view_get", "exists", "get_metadata", "onchange", "web_search_read",
}


class OdooError(Exception):
    """Server-side fault. `name` is the Python exception class, e.g. odoo.exceptions.AccessError."""

    def __init__(self, name: str, message: str, debug: str = ""):
        super().__init__(f"{name}: {message}")
        self.name = name
        self.message = message
        self.debug = debug

    @property
    def is_access(self) -> bool:
        return self.name.endswith(("AccessError", "AccessDenied"))

    @property
    def is_missing_model(self) -> bool:
        return "KeyError" in self.name or "doesn't exist" in self.message or (
            "Object" in self.message and "doesn't exist" in self.message
        )


class ConfigError(Exception):
    pass


def load_config(profile: str | None = None) -> dict:
    """Profile file first, env overrides it. Refuses a profile file readable by others."""
    profile = profile or os.environ.get("ODOO_PROFILE", "default")
    cfg: dict = {}
    path = CONFIG_DIR / profile
    if path.exists():
        mode = path.stat().st_mode
        if mode & (stat.S_IRGRP | stat.S_IROTH):
            raise ConfigError(f"{path} is readable by others; run: chmod 600 {path}")
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip().strip('"').strip("'")
    for k in KEYS + ("ODOO_PASSWORD", "ODOO_TIMEOUT", "ODOO_COMPANY_IDS", "ODOO_LANG"):
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    if not cfg.get("ODOO_API_KEY") and cfg.get("ODOO_PASSWORD"):
        cfg["ODOO_API_KEY"] = cfg["ODOO_PASSWORD"]
    cfg["profile"] = profile
    cfg["path"] = str(path)
    return cfg


def http_transport(url: str, payload: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:300]
        raise OdooError("HTTPError", f"{e.code} {e.reason} at {url}: {body}") from None
    except urllib.error.URLError as e:
        raise OdooError("URLError", f"{e.reason} at {url}") from None
    except (TimeoutError, OSError) as e:
        raise OdooError("NetworkError", f"{e} at {url}") from None
    except ValueError as e:  # JSONDecodeError, UnicodeDecodeError: proxy/login page, not Odoo
        raise OdooError("BadResponse", f"not a JSON-RPC answer from {url}: {e}") from None


class Odoo:
    def __init__(self, url: str, db: str = "", user: str = "", key: str = "",
                 timeout: float = 30, transport=http_transport, context: dict | None = None):
        self.url = url.rstrip("/")
        host = urllib.parse.urlsplit(self.url).hostname or ""
        if self.url.startswith("http://") and host not in ("localhost", "127.0.0.1") \
                and not os.environ.get("ODOO_ALLOW_HTTP"):
            raise ConfigError(f"{self.url} is plain http: the API key would travel unencrypted. "
                              "Use https (or set ODOO_ALLOW_HTTP=1 for a private network)")
        self.db, self.user, self.key = db, user, key
        self.timeout = timeout
        self.transport = transport
        self.context = context or {}
        self.uid: int | None = None
        self._ids = itertools.count(1)

    @classmethod
    def from_config(cls, cfg: dict, transport=http_transport) -> "Odoo":
        missing = [k for k in KEYS if not cfg.get(k)]
        if missing:
            raise ConfigError(
                f"missing {', '.join(missing)} (env or {cfg.get('path')}); "
                "collect them with request_secret, never in chat"
            )
        ctx: dict = {}
        if cfg.get("ODOO_COMPANY_IDS"):
            ctx["allowed_company_ids"] = [int(x) for x in cfg["ODOO_COMPANY_IDS"].split(",")]
        if cfg.get("ODOO_LANG"):
            ctx["lang"] = cfg["ODOO_LANG"]
        return cls(cfg["ODOO_URL"], cfg["ODOO_DB"], cfg["ODOO_USER"], cfg["ODOO_API_KEY"],
                   float(cfg.get("ODOO_TIMEOUT", 30)), transport, ctx)

    # -- transport -------------------------------------------------------
    def rpc(self, service: str, method: str, *args):
        payload = {"jsonrpc": "2.0", "method": "call",
                   "params": {"service": service, "method": method, "args": list(args)},
                   "id": next(self._ids)}
        resp = self.transport(self.url + "/jsonrpc", payload, self.timeout)
        if resp.get("error"):
            err = resp["error"]
            data = err.get("data") or {}
            raise OdooError(data.get("name") or str(err.get("code")),
                            data.get("message") or err.get("message", ""),
                            data.get("debug", ""))
        return resp.get("result")

    def version(self) -> dict:
        return self.rpc("common", "version")

    def list_dbs(self) -> list:
        return self.rpc("db", "list")

    def login(self) -> int:
        if self.uid is None:
            uid = self.rpc("common", "authenticate", self.db, self.user, self.key, {})
            if not uid:
                raise OdooError("AccessDenied", "login failed: wrong db, user or API key "
                                "(or the plan/hosting blocks the external API)")
            self.uid = uid
        return self.uid

    def execute(self, model: str, method: str, *args, **kwargs):
        self.login()
        if self.context:
            kwargs["context"] = {**self.context, **kwargs.get("context", {})}
        return self.rpc("object", "execute_kw", self.db, self.uid, self.key,
                        model, method, list(args), kwargs)

    # -- helpers ---------------------------------------------------------
    def search_read(self, model, domain=None, fields=None, limit=80, offset=0, order=None, **kw):
        opts = {"fields": fields or [], "limit": limit, "offset": offset, **kw}
        if order:
            opts["order"] = order
        return self.execute(model, "search_read", domain or [], **opts)

    def count(self, model, domain=None) -> int:
        return self.execute(model, "search_count", domain or [])

    def fields(self, model, attributes=None) -> dict:
        attrs = attributes or ["string", "type", "required", "readonly", "relation",
                               "selection", "store", "help"]
        return self.execute(model, "fields_get", attributes=attrs)

    def can(self, model: str, op: str) -> bool:
        return bool(self.execute(model, "check_access_rights", op, raise_exception=False))

    def model_exists(self, model: str) -> bool:
        try:
            return bool(self.count("ir.model", [("model", "=", model)]))
        except OdooError as e:
            if not e.is_access:
                raise
        try:  # ir.model unreadable for this user: probe the model itself
            self.execute(model, "check_access_rights", "read", raise_exception=False)
            return True
        except OdooError:
            return False

    def redacted(self) -> dict:
        return {"url": self.url, "db": self.db, "user": self.user,
                "key": ("set, " + str(len(self.key)) + " chars") if self.key else "missing"}
