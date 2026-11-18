"""Read-only audit of an Odoo database and gap check against an app's needs.

Every section catches AccessError and missing models, and reports them as findings instead
of crashing: the integration user is usually limited, and "cannot read X" is itself a fact
the owner needs.
"""
from __future__ import annotations

import datetime as dt

from odoo_client import Odoo, OdooError

# Models an outside app usually touches. Missing ones are simply not installed.
KEY_MODELS = [
    "res.partner", "res.company", "res.users", "product.template", "product.product",
    "sale.order", "sale.order.line", "purchase.order", "purchase.order.line",
    "account.move", "account.move.line", "account.payment", "account.journal",
    "account.tax", "stock.picking", "stock.move", "stock.quant", "stock.warehouse",
    "fleet.vehicle", "fleet.vehicle.log.services", "fleet.vehicle.log.contract",
    "fleet.vehicle.odometer", "hr.employee", "hr.expense", "crm.lead", "project.project",
    "project.task", "mrp.production", "pos.order", "helpdesk.ticket", "mail.message",
]
OPS = ("read", "write", "create", "unlink")


def _utc(days_ago: int) -> str:
    t = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_ago)
    return t.strftime("%Y-%m-%d %H:%M:%S")


class Audit:
    def __init__(self, odoo: Odoo, models: list[str] | None = None, sample: int = 0):
        self.o = odoo
        self.models = models or KEY_MODELS
        self.sample = sample
        self.report: dict = {"sections": {}, "findings": []}
        self._exists: dict[str, bool] = {}
        self.denied: list[str] = []
        self._read: dict[str, bool] = {}

    # -- plumbing --------------------------------------------------------
    def find(self, severity: str, kind: str, text: str, action: str = ""):
        """severity: high|medium|low|info. kind: fix|connect|access|info."""
        self.report["findings"].append(
            {"severity": severity, "kind": kind, "text": text, "action": action})

    def safe(self, label: str, fn, default=None):
        try:
            return fn()
        except OdooError as e:
            if e.is_access:
                self.denied.append(label)
            else:
                self.find("low", "info", f"{label}: {e.name}: {e.message[:160]}")
            return default

    def exists(self, model: str) -> bool:
        if model not in self._exists:
            try:
                self._exists[model] = self.o.model_exists(model)
            except OdooError:
                self._exists[model] = False
        return self._exists[model]

    # -- sections --------------------------------------------------------
    def run(self) -> dict:
        s = self.report["sections"]
        s["server"] = self.server()
        s["user"] = self.user()
        s["companies"] = self.safe("res.company", self.companies, [])
        s["modules"] = self.safe("ir.module.module", self.modules, {})
        s["custom"] = self.safe("ir.model / ir.model.fields", self.custom, {})
        s["models"] = self.inventory()
        s["automation"] = self.automation()
        s["integrations"] = self.integrations()
        s["health"] = self.health()
        if self.denied:
            self.find("medium", "access", "integration user cannot read: " +
                      ", ".join(dict.fromkeys(self.denied)),
                      "fine if the app never needs them; for a full audit run it as an admin")
        order = {"high": 0, "medium": 1, "low": 2, "info": 3}
        self.report["findings"].sort(key=lambda f: order.get(f["severity"], 9))
        return self.report

    def server(self) -> dict:
        v = self.o.version()
        info = {**self.o.redacted(), "server_version": v.get("server_version"),
                "server_serie": v.get("server_serie"), "protocol": v.get("protocol_version")}
        major = str(v.get("server_serie", "")).split(".")[0].replace("saas~", "")
        if major.isdigit() and int(major) >= 19:
            self.find("medium", "fix", f"Odoo {v.get('server_serie')}: /jsonrpc and /xmlrpc are "
                      "deprecated from 19", "plan the move to the JSON-2 API (/json/2/)")
        elif major.isdigit() and int(major) < 14:
            self.find("medium", "info", f"Odoo {v.get('server_serie')}: no API keys before 14",
                      "the integration needs the user password")
        return info

    def user(self) -> dict:
        uid = self.o.login()
        u = self.o.execute("res.users", "read", [uid],
                           fields=["name", "login", "company_id", "company_ids", "groups_id",
                                   "lang", "tz", "share"])[0]
        # en_US so the admin check works whatever the user's or profile's language
        groups = self.safe("res.groups", lambda: [g["full_name"] for g in self.o.execute(
            "res.groups", "read", u["groups_id"], fields=["full_name"],
            context={"lang": "en_US"})], [])
        admin = any(g in ("Administration / Settings", "Administration / Access Rights")
                    for g in groups)
        if admin:
            self.find("medium", "fix", "integration user has Administration rights",
                      "use a dedicated user with only the app groups it needs")
        if u.get("share"):
            self.find("high", "fix", "integration user is a portal/public (share) user",
                      "use an internal user")
        if not u.get("tz"):
            self.find("low", "info", "integration user has no timezone",
                      "set tz; API datetimes are UTC either way")
        return {"uid": uid, "name": u["name"], "login": u["login"],
                "company": u["company_id"], "company_ids": u["company_ids"],
                "lang": u.get("lang"), "tz": u.get("tz"), "admin": admin, "groups": groups}

    def companies(self) -> list:
        rows = self.o.search_read("res.company", [], ["name", "currency_id", "country_id",
                                                      "vat"], limit=50)
        if len(rows) > 1:
            self.find("info", "connect", f"{len(rows)} companies",
                      "pass context allowed_company_ids on every call and set company_id on "
                      "every create")
        return rows

    def modules(self) -> dict:
        rows = self.o.search_read("ir.module.module", [("state", "=", "installed")],
                                  ["name", "shortdesc", "author", "application",
                                   "installed_version"], limit=2000, order="name")
        apps = [r["name"] for r in rows if r.get("application")]
        third = [{"name": r["name"], "author": r.get("author") or "?",
                  "version": r.get("installed_version")}
                 for r in rows if "Odoo S.A." not in (r.get("author") or "")]
        pending = self.o.search_read(
            "ir.module.module", [("state", "in", ["to upgrade", "to install", "to remove"])],
            ["name", "state"], limit=100)
        for p in pending:
            self.find("high", "fix", f"module {p['name']} stuck in state '{p['state']}'",
                      "finish or cancel the pending module operation (Apps menu)")
        if third:
            self.find("info", "info", f"{len(third)} non-Odoo-S.A. modules installed",
                      "read their models before mapping; they may own the data you need")
        return {"installed": len(rows), "apps": apps, "third_party": third,
                "pending": pending}

    def custom(self) -> dict:
        models = self.o.search_read("ir.model", [("state", "=", "manual")],
                                    ["model", "name"], limit=500)
        fields = self.o.search_read("ir.model.fields", [("state", "=", "manual")],
                                    ["model", "name", "field_description", "ttype",
                                     "relation", "required"], limit=2000, order="model,name")
        by_model: dict = {}
        for f in fields:
            by_model.setdefault(f["model"], []).append(
                {"name": f["name"], "label": f["field_description"], "type": f["ttype"],
                 "relation": f.get("relation") or "", "required": f["required"]})
        if models or fields:
            self.find("info", "connect",
                      f"{len(models)} custom models and {len(fields)} custom x_ fields "
                      "(Studio or manual)", "map them explicitly; the client's real data "
                      "often lives there")
        return {"models": models, "fields": by_model}

    def inventory(self) -> list:
        out = []
        for m in self.models:
            if not self.exists(m):
                continue
            row: dict = {"model": m}
            try:
                row["access"] = {op: self.o.can(m, op) for op in OPS}
            except OdooError as e:
                row["access"] = {"error": e.name}
            self._read[m] = bool(row["access"].get("read"))
            if row["access"].get("read"):
                try:
                    row["count"] = self.o.count(m)
                    if row["count"] == 0 and not self.report["sections"]["user"]["admin"]:
                        self.find("low", "access", f"{m}: readable but 0 records visible",
                                  "record rules or company restrictions may hide data from this "
                                  "user; compare with an admin count")
                    if self.sample:
                        row["sample"] = self.o.search_read(m, [], [], limit=self.sample,
                                                           order="id desc")
                except OdooError as e:
                    row["count"] = f"error: {e.name}"
            else:
                row["count"] = None
            out.append(row)
        return out

    def automation(self) -> dict:
        res: dict = {}
        if self.exists("ir.cron"):
            crons = self.safe("ir.cron", lambda: self.o.search_read(
                "ir.cron", [("active", "=", True)],
                ["name", "model_id", "interval_number", "interval_type", "nextcall"],
                limit=300, order="nextcall"))
            stuck = [c for c in crons or [] if c.get("nextcall") and c["nextcall"] < _utc(1)]
            for c in stuck:
                self.find("high", "fix", f"cron '{c['name']}' is overdue (nextcall "
                          f"{c['nextcall']} UTC)", "check the server log; the cron worker may "
                          "be down or the job keeps failing")
            res["crons"] = crons
        if self.exists("base.automation"):
            res["automated_actions"] = self.safe("base.automation", lambda: self.o.search_read(
                "base.automation", [], ["name", "model_id", "trigger", "active", "state"],
                limit=300))
        if self.exists("ir.actions.server"):
            res["server_actions_code"] = self.safe("ir.actions.server", lambda: self.o.count(
                "ir.actions.server", [("state", "=", "code")]))
        return res

    def integrations(self) -> dict:
        res: dict = {}
        checks = {
            "ir.mail_server": (["name", "smtp_host", "active"], []),
            "fetchmail.server": (["name", "server", "state", "date"], []),
            "payment.provider": (["name", "state", "code"], [("state", "!=", "disabled")]),
            "iap.account": (["service_name"], []),
        }
        for model, (fields, dom) in checks.items():
            if self.exists(model):
                res[model] = self.safe(model, lambda m=model, f=fields, d=dom:
                                       self.o.search_read(m, d, f, limit=50))
        if "ir.mail_server" in res and res["ir.mail_server"] == []:
            self.find("low", "info", "no outgoing mail server record",
                      "Odoo Online sends anyway; self-hosted needs one for emails")
        if self.exists("ir.config_parameter"):
            base = self.safe("ir.config_parameter", lambda: self.o.search_read(
                "ir.config_parameter", [("key", "=", "web.base.url")], ["value"], limit=1))
            if base:
                res["web.base.url"] = base[0]["value"]
                if base[0]["value"].startswith("http://localhost"):
                    self.find("medium", "fix", "web.base.url points to localhost",
                              "set it to the public URL; links in emails and portal break")
        return res

    def readable(self, model) -> bool:
        return self.exists(model) and self._read.get(model, True)

    def _count_check(self, model, domain, severity, kind, text, action):
        if not self.readable(model):
            return None
        n = self.safe(f"{model} check", lambda: self.o.count(model, domain))
        if n:
            self.find(severity, kind, text.format(n=n), action)
        return n

    def _dupes(self, model, field, domain):
        if not self.readable(model):
            return None
        rows = self.safe(f"{model} duplicates", lambda: self.o.execute(
            model, "read_group", domain + [(field, "!=", False)], [field], [field],
            lazy=True), [])  # no limit: 16 cannot order groups by count server-side
        d = [r for r in rows or [] if r.get(f"{field}_count", r.get("__count", 0)) > 1]
        if d:
            self.find("medium", "fix", f"{len(d)} duplicate {model}.{field} values "
                      f"(e.g. {d[0].get(field)!r})", "merge duplicates before syncing, or the "
                      "app will match the wrong record")
        return len(d)

    def health(self) -> dict:
        h: dict = {}
        h["mail_exceptions"] = self._count_check(
            "mail.mail", [("state", "=", "exception")], "medium", "fix",
            "{n} emails failed to send (mail.mail state=exception)",
            "fix the mail server, then resend from Settings > Technical > Emails")
        h["dup_partner_email"] = self._dupes("res.partner", "email", [("active", "=", True)])
        h["dup_partner_vat"] = self._dupes("res.partner", "vat", [("active", "=", True)])
        h["dup_product_code"] = self._dupes("product.product", "default_code",
                                            [("active", "=", True)])
        h["products_no_code"] = self._count_check(
            "product.product", [("default_code", "=", False), ("active", "=", True)],
            "low", "fix", "{n} active products without an internal reference",
            "set default_code; an outside app needs a stable key to match products")
        h["vehicles_no_plate"] = self._count_check(
            "fleet.vehicle", [("license_plate", "=", False)], "low", "fix",
            "{n} vehicles without a license plate", "fill license_plate; apps match trucks "
            "by plate")
        h["old_draft_invoices"] = self._count_check(
            "account.move", [("state", "=", "draft"), ("create_date", "<", _utc(30)),
                             ("move_type", "in", ["out_invoice", "in_invoice", "out_refund",
                                                  "in_refund"])],
            "medium", "fix", "{n} invoices/bills in draft for more than 30 days",
            "post or delete them; drafts hide real receivables/payables")
        h["old_rfq"] = self._count_check(
            "purchase.order", [("state", "in", ["draft", "sent"]),
                               ("create_date", "<", _utc(30))], "low", "fix",
            "{n} RFQs older than 30 days still open", "confirm or cancel them")
        h["negative_stock"] = self._count_check(
            "stock.quant", [("quantity", "<", 0), ("location_id.usage", "=", "internal")],
            "medium", "fix", "{n} negative stock quants in internal locations",
            "receive missing stock or fix the moves; inventory value is wrong")
        h["overdue_customer_invoices"] = self._count_check(
            "account.move", [("move_type", "=", "out_invoice"), ("state", "=", "posted"),
                             ("payment_state", "in", ["not_paid", "partial"]),
                             ("invoice_date_due", "<", _utc(0)[:10])],
            "info", "info", "{n} posted customer invoices overdue", "")
        return h


# Re-exported so callers keep one import.
from odoo_gap import gap, gap_markdown  # noqa: E402,F401
from odoo_report import dump, to_markdown  # noqa: E402,F401
