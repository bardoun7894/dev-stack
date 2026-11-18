"""Offline tests with a fake transport. Run: python3 -m unittest test_odoo -v (from scripts/)."""
from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import odoo as cli  # noqa: E402
import odoo_client  # noqa: E402
from odoo_audit import Audit, gap  # noqa: E402
from odoo_client import ConfigError, Odoo, OdooError, load_config  # noqa: E402

ACCESS = {"name": "odoo.exceptions.AccessError", "message": "You are not allowed",
          "debug": ""}


class Fake:
    """Answers execute_kw from a table {(model, method): result or Exception-dict}."""

    def __init__(self, table=None, uid=7):
        self.table = table or {}
        self.uid = uid
        self.calls = []

    def __call__(self, url, payload, timeout):
        p = payload["params"]
        self.calls.append(p)
        if p["service"] == "common" and p["method"] == "version":
            return {"result": {"server_version": "16.0", "server_serie": "16.0",
                               "protocol_version": 1}}
        if p["service"] == "common" and p["method"] == "authenticate":
            return {"result": self.uid}
        if p["service"] == "db":
            return {"error": {"code": 200, "message": "Odoo Server Error",
                              "data": {"name": "odoo.exceptions.AccessDenied",
                                       "message": "Access Denied"}}}
        model, method = p["args"][3], p["args"][4]
        r = self.table.get((model, method), self.table.get((model, "*")))
        if r is None:
            if method == "check_access_rights":
                return {"result": True}
            if method in ("search_count",):
                return {"result": 0}
            if method in ("search_read", "read_group"):
                return {"result": []}
            return {"result": None}
        if isinstance(r, dict) and r.get("__error__"):
            return {"error": {"code": 200, "message": "Odoo Server Error", "data": r["data"]}}
        return {"result": r(p["args"]) if callable(r) else r}


def err(data):
    return {"__error__": True, "data": data}


def mk(table=None):
    f = Fake(table)
    return Odoo("http://x", "db", "u", "secretkey", transport=f), f


class ClientTests(unittest.TestCase):
    def test_execute_kw_shape_and_context(self):
        o, f = mk({("res.partner", "search_count"): 3})
        o.context = {"allowed_company_ids": [1]}
        self.assertEqual(o.count("res.partner", [["is_company", "=", True]]), 3)
        args = f.calls[-1]["args"]
        self.assertEqual(args[:5], ["db", 7, "secretkey", "res.partner", "search_count"])
        self.assertEqual(args[6]["context"], {"allowed_company_ids": [1]})

    def test_error_maps_to_odooerror(self):
        o, _ = mk({("account.move", "search_read"): err(ACCESS)})
        with self.assertRaises(OdooError) as cm:
            o.search_read("account.move")
        self.assertTrue(cm.exception.is_access)

    def test_failed_login(self):
        f = Fake(uid=False)
        o = Odoo("http://x", "db", "u", "bad", transport=f)
        with self.assertRaises(OdooError):
            o.login()

    def test_redacted_hides_key(self):
        o, _ = mk()
        self.assertNotIn("secretkey", str(o.redacted()))


class ConfigTests(unittest.TestCase):
    def test_profile_file_and_env_override(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "client"
            p.write_text("ODOO_URL=https://a\nODOO_DB=a\nODOO_USER=api\nODOO_API_KEY='k'\n")
            os.chmod(p, 0o600)
            with mock.patch.object(odoo_client, "CONFIG_DIR", Path(d)), \
                    mock.patch.dict(os.environ, {"ODOO_DB": "b"}, clear=False):
                cfg = load_config("client")
            self.assertEqual((cfg["ODOO_URL"], cfg["ODOO_DB"], cfg["ODOO_API_KEY"]),
                             ("https://a", "b", "k"))

    def test_world_readable_profile_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "default"
            p.write_text("ODOO_URL=x\n")
            os.chmod(p, 0o644)
            with mock.patch.object(odoo_client, "CONFIG_DIR", Path(d)):
                with self.assertRaises(ConfigError):
                    load_config("default")

    def test_missing_keys(self):
        with self.assertRaises(ConfigError):
            Odoo.from_config({"ODOO_URL": "x", "path": "p"})


class AuditTests(unittest.TestCase):
    def test_limited_user_audit_does_not_crash(self):
        """Non-admin: ir.* unreadable. Audit must finish and report access findings."""
        t = {
            ("res.users", "read"): [{"id": 7, "name": "API", "login": "api",
                                     "company_id": [1, "C"], "company_ids": [1],
                                     "groups_id": [1], "lang": "fr_FR", "tz": False,
                                     "share": False}],
            ("res.groups", "read"): [{"id": 1, "full_name": "Fleet / User"}],
            ("ir.module.module", "*"): err(ACCESS),
            ("ir.model", "*"): err(ACCESS),
            ("ir.model.fields", "*"): err(ACCESS),
            ("ir.cron", "*"): err(ACCESS),
            ("fleet.vehicle", "search_count"): 12,
        }
        o, _ = mk(t)
        rep = Audit(o, ["fleet.vehicle"]).run()
        kinds = [f["kind"] for f in rep["findings"]]
        self.assertIn("access", kinds)
        self.assertEqual(rep["sections"]["models"][0]["count"], 12)

    def test_admin_and_overdue_cron_findings(self):
        t = {
            ("res.users", "read"): [{"id": 2, "name": "A", "login": "admin",
                                     "company_id": [1, "C"], "company_ids": [1],
                                     "groups_id": [3], "lang": "en_US", "tz": "UTC",
                                     "share": False}],
            ("res.groups", "read"): [{"id": 3, "full_name": "Administration / Settings"}],
            ("ir.model", "search_count"): 1,
            ("ir.cron", "search_read"): [{"name": "Mail queue", "model_id": [1, "m"],
                                          "interval_number": 1, "interval_type": "hours",
                                          "nextcall": "2020-01-01 00:00:00"}],
        }
        o, _ = mk(t)
        rep = Audit(o, []).run()
        texts = " ".join(f["text"] for f in rep["findings"])
        self.assertIn("Administration rights", texts)
        self.assertIn("overdue", texts)
        self.assertEqual(rep["findings"][0]["severity"], "high")

    def test_gap_reports_missing_field_and_required(self):
        t = {
            ("ir.model", "search_count"): lambda a: 1 if a[5][0][0][2] == "fleet.vehicle" else 0,
            ("ir.module.module", "search_read"): [{"name": "fleet", "state": "installed"}],
            ("fleet.vehicle", "fields_get"): {
                "license_plate": {"type": "char", "required": False},
                "model_id": {"type": "many2one", "required": True,
                             "relation": "fleet.vehicle.model"},
                "id": {"type": "integer", "required": False}},
        }
        o, _ = mk(t)
        g = gap(o, {"modules": ["fleet", "purchase"],
                    "models": {"fleet.vehicle": {"fields": ["license_plate", "x_gps"],
                                                 "ops": ["read", "create"]},
                               "x_fuel.log": {"fields": ["x_name"]}}})
        self.assertFalse(g["ok"])
        fv = g["models"][0]
        self.assertEqual(fv["missing_fields"], ["x_gps"])
        self.assertEqual(fv["required_unmapped"], ["model_id"])
        self.assertEqual(g["models"][1]["problem"], "model not installed")
        self.assertEqual(g["modules"][1]["state"], "not found")


class CliGuardTests(unittest.TestCase):
    def run_cli(self, argv, table=None):
        o, f = mk(table)
        args = cli.argparse.Namespace  # noqa: F841
        with mock.patch.object(cli, "load_config", return_value={}), \
                mock.patch.object(cli.Odoo, "from_config", return_value=o):
            buf, ebuf = io.StringIO(), io.StringIO()
            with redirect_stdout(buf), redirect_stderr(ebuf):
                try:
                    code = cli.main(argv)
                except SystemExit as e:
                    code = e.code
        return code, buf.getvalue(), ebuf.getvalue(), f

    def test_create_refused_without_yes(self):
        code, _, _, f = self.run_cli(["create", "res.partner", '{"name": "X"}'])
        self.assertIn("refused", str(code))
        self.assertFalse([c for c in f.calls if c["service"] == "object"])

    def test_dry_run_sends_nothing(self):
        code, out, _, f = self.run_cli(["--dry-run", "write", "res.partner", "1,2",
                                        '{"name": "Y"}'])
        self.assertIn("DRY RUN", out)
        self.assertFalse([c for c in f.calls if c["service"] == "object"])

    def test_create_with_yes(self):
        code, out, _, f = self.run_cli(["--yes", "create", "res.partner", '{"name": "X"}'],
                                       {("res.partner", "create"): 42})
        self.assertEqual(code, 0)
        self.assertIn("42", out)

    def test_call_read_method_needs_no_yes(self):
        code, _, _, _ = self.run_cli(["call", "res.partner", "search_count", "[[]]"])
        self.assertEqual(code, 0)

    def test_call_write_method_refused(self):
        code, _, _, _ = self.run_cli(["call", "account.move", "action_post", "[[5]]"])
        self.assertIn("refused", str(code))

    def test_python_literal_domain(self):
        code, _, _, f = self.run_cli(["count", "res.partner", "[('is_company','=',True)]"])
        self.assertEqual(f.calls[-1]["args"][5], [[("is_company", "=", True)]])


if __name__ == "__main__":
    unittest.main()
