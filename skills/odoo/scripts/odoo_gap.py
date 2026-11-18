"""Gap check: does this Odoo have the modules, models, fields and rights an app needs?"""
from __future__ import annotations

from odoo_client import Odoo, OdooError

def gap(odoo: Odoo, spec: dict) -> dict:
    """spec = {"modules": [...], "models": {"fleet.vehicle": {"fields": [...], "ops": [...]}}}"""
    out: dict = {"modules": [], "models": [], "ok": True}
    if spec.get("modules"):
        try:
            rows = odoo.search_read("ir.module.module", [("name", "in", spec["modules"])],
                                    ["name", "state"], limit=len(spec["modules"]))
            st = {r["name"]: r["state"] for r in rows}
        except OdooError as e:
            st = {m: f"unknown ({e.name})" for m in spec["modules"]}
        for m in spec["modules"]:
            state = st.get(m, "not found")
            out["modules"].append({"module": m, "state": state})
            if state != "installed":
                out["ok"] = False
    for model, need in (spec.get("models") or {}).items():
        row: dict = {"model": model, "exists": odoo.model_exists(model)}
        if not row["exists"]:
            row["problem"] = "model not installed"
            out["ok"] = False
            out["models"].append(row)
            continue
        row["access"] = {}
        for op in need.get("ops", ["read"]):
            try:
                row["access"][op] = odoo.can(model, op)
            except OdooError as e:
                row["access"][op] = f"error: {e.name}"
            if row["access"][op] is not True:
                out["ok"] = False
        try:
            fields = odoo.fields(model, ["type", "required", "relation", "selection",
                                         "readonly", "string"])
        except OdooError as e:
            row["problem"] = f"fields_get: {e.name}"
            out["ok"] = False
            out["models"].append(row)
            continue
        wanted = need.get("fields", [])
        row["missing_fields"] = [f for f in wanted if f not in fields]
        if row["missing_fields"]:
            out["ok"] = False
        if "create" in need.get("ops", []):
            req = sorted(f for f, a in fields.items()
                         if a.get("required") and f not in wanted
                         and f not in ("id", "create_uid", "write_uid", "create_date",
                                       "write_date"))
            try:  # fields Odoo fills by itself on create are not a gap
                defaults = (odoo.execute(model, "default_get", req) if req else {}) or {}
            except OdooError:
                defaults = {}
            row["required_defaulted"] = [f for f in req if f in defaults]
            row["required_unmapped"] = [f for f in req if f not in defaults]
            if row["required_unmapped"]:
                out["ok"] = False
        row["fields"] = {f: {k: fields[f].get(k) for k in ("type", "required", "relation")}
                         for f in wanted if f in fields}
        out["models"].append(row)
    return out


def gap_markdown(g: dict) -> str:
    lines = [f"# Gap check: {'OK' if g['ok'] else 'GAPS FOUND'}", ""]
    for m in g["modules"]:
        lines.append(f"- module {m['module']}: {m['state']}")
    for m in g["models"]:
        if not m["exists"] or m.get("problem"):
            lines.append(f"- {m['model']}: {m.get('problem')}")
            continue
        acc = ", ".join(f"{k}={'yes' if v is True else v if isinstance(v, str) else 'no'}"
                        for k, v in m["access"].items())
        lines.append(f"- {m['model']}: access {acc}")
        if m.get("missing_fields"):
            lines.append(f"  - missing fields: {', '.join(m['missing_fields'])}")
        if m.get("required_unmapped"):
            lines.append(f"  - required on create, no default, not in your mapping: "
                         f"{', '.join(m['required_unmapped'])}")
        if m.get("required_defaulted"):
            lines.append(f"  - required but Odoo fills a default: "
                         f"{', '.join(m['required_defaulted'])} (check the default is right)")
    return "\n".join(lines) + "\n"
