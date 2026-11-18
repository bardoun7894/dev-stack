#!/usr/bin/env python3
"""odoo.py: read, audit and (guarded) write an Odoo database through the external API.

Read-only by default. create / write / unlink / any non-read `call` need --yes, and print
the payload (key redacted) with --dry-run. Credentials: env or ~/.config/odoo/<profile>.
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from odoo_audit import Audit, dump, gap, gap_markdown, to_markdown  # noqa: E402
from odoo_client import (READ_METHODS, ConfigError, Odoo, OdooError,  # noqa: E402
                         load_config)


def parse_value(text: str | None, default):
    """JSON first, then a Python literal (domains are often written with tuples)."""
    if text is None or text == "":
        return default
    if text == "-":
        text = sys.stdin.read()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return ast.literal_eval(text)


def out(args, data, md: str | None = None):
    if args.json or md is None:
        print(dump(data))
    else:
        print(md, end="")


def table(rows: list, cols: list[str]) -> str:
    def cell(v):
        if isinstance(v, list) and len(v) == 2 and isinstance(v[0], int) \
                and isinstance(v[1], str):
            v = v[1]  # many2one -> display name
        s = "" if v is False or v is None else str(v)
        return s.replace("\n", " ")[:60]
    w = {c: max([len(c)] + [len(cell(r.get(c))) for r in rows]) for c in cols}
    lines = ["  ".join(c.ljust(w[c]) for c in cols)]
    lines += ["  ".join(cell(r.get(c)).ljust(w[c]) for c in cols) for r in rows]
    return "\n".join(lines) + "\n"


def guard(args, what: str, payload) -> bool:
    if args.dry_run:
        print(f"DRY RUN {what}:\n{dump(payload)}")
        return False
    if not args.yes:
        sys.exit(f"refused: {what} changes data in Odoo. Show --dry-run to the owner, "
                 "then rerun with --yes after they confirm this exact action.")
    return True


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="odoo.py", description=__doc__.splitlines()[0])
    p.add_argument("--profile", help="config file ~/.config/odoo/NAME (default: default)")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--yes", action="store_true", help="allow a write (owner confirmed)")
    p.add_argument("--dry-run", action="store_true", help="print the write, do not send")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("config", help="show resolved config (key redacted)")
    sub.add_parser("version", help="server version, no login needed")
    sub.add_parser("dbs", help="list databases (often disabled with list_db=False)")
    sub.add_parser("whoami", help="login and show user, groups, companies")

    s = sub.add_parser("modules", help="installed modules")
    s.add_argument("--apps", action="store_true", help="applications only")
    s.add_argument("--search")
    s.add_argument("--all-states", action="store_true")

    s = sub.add_parser("models", help="models from ir.model")
    s.add_argument("--search", help="substring of model or name")
    s.add_argument("--custom", action="store_true", help="state=manual (x_ / Studio) only")

    s = sub.add_parser("fields", help="fields_get of a model")
    s.add_argument("model")
    s.add_argument("--required", action="store_true")
    s.add_argument("--custom", action="store_true", help="x_ fields only")
    s.add_argument("--search")

    s = sub.add_parser("count", help="search_count")
    s.add_argument("model")
    s.add_argument("domain", nargs="?")

    s = sub.add_parser("read", help="search_read, paged")
    s.add_argument("model")
    s.add_argument("domain", nargs="?")
    s.add_argument("--fields", default="", help="comma list; default: display_name")
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--offset", type=int, default=0)
    s.add_argument("--order")

    s = sub.add_parser("get", help="read records by id")
    s.add_argument("model")
    s.add_argument("ids", nargs="+", type=int)
    s.add_argument("--fields", default="")

    s = sub.add_parser("group", help="read_group counts, e.g. group res.partner country_id")
    s.add_argument("model")
    s.add_argument("groupby")
    s.add_argument("domain", nargs="?")
    s.add_argument("--limit", type=int, default=50)

    s = sub.add_parser("xmlid", help="resolve external id(s) module.name, or find ids of "
                       "a record: xmlid MODEL ID")
    s.add_argument("ref", nargs="+")

    s = sub.add_parser("access", help="read/write/create/unlink rights of the API user")
    s.add_argument("models", nargs="+")

    s = sub.add_parser("audit", help="full read-only audit: modules, custom, rights, health")
    s.add_argument("--models", help="comma list to replace the default key models")
    s.add_argument("--sample", type=int, default=0, help="N latest records per model")
    s.add_argument("--out", help="directory: writes audit.json and audit.md")

    s = sub.add_parser("gap", help="check an app's needs (JSON spec) against this Odoo")
    s.add_argument("spec", help="path to JSON, or - for stdin")

    s = sub.add_parser("create", help="create records (needs --yes)")
    s.add_argument("model")
    s.add_argument("values", help="JSON dict or list of dicts, or - for stdin")

    s = sub.add_parser("write", help="write values to ids (needs --yes)")
    s.add_argument("model")
    s.add_argument("ids", help="comma list")
    s.add_argument("values")

    s = sub.add_parser("unlink", help="delete ids (needs --yes)")
    s.add_argument("model")
    s.add_argument("ids", help="comma list")

    s = sub.add_parser("call", help="any model method: call MODEL METHOD [ARGS] [KWARGS]")
    s.add_argument("model")
    s.add_argument("method")
    s.add_argument("args", nargs="?")
    s.add_argument("kwargs", nargs="?")

    args = p.parse_args(argv)
    try:
        cfg = load_config(args.profile)
        if args.cmd == "config":
            red = {k: v for k, v in cfg.items() if k not in ("ODOO_API_KEY", "ODOO_PASSWORD")}
            red["ODOO_API_KEY"] = "set" if cfg.get("ODOO_API_KEY") else "missing"
            out(args, red)
            return 0
        if args.cmd in ("version", "dbs"):
            o = Odoo(cfg.get("ODOO_URL") or sys.exit("ODOO_URL missing"))
        else:
            o = Odoo.from_config(cfg)
        return run(args, o)
    except ConfigError as e:
        print(f"config: {e}", file=sys.stderr)
        return 2
    except (ValueError, SyntaxError) as e:
        print(f"bad argument (expected JSON or a Python literal): {e}", file=sys.stderr)
        return 2
    except OdooError as e:
        print(f"odoo: {e}", file=sys.stderr)
        if e.is_access:
            print("hint: the API user lacks this right; see `access MODEL`", file=sys.stderr)
        return 1


def run(args, o: Odoo) -> int:
    c = args.cmd
    if c == "version":
        out(args, o.version())
    elif c == "dbs":
        out(args, o.list_dbs())
    elif c == "whoami":
        a = Audit(o)
        u = a.user()
        out(args, {**u, "findings": a.report["findings"]})
    elif c == "modules":
        dom = [] if args.all_states else [("state", "=", "installed")]
        if args.apps:
            dom.append(("application", "=", True))
        if args.search:
            dom += ["|", ("name", "ilike", args.search), ("shortdesc", "ilike", args.search)]
        rows = o.search_read("ir.module.module", dom,
                             ["name", "shortdesc", "state", "author", "installed_version"],
                             limit=2000, order="name")
        out(args, rows, table(rows, ["name", "shortdesc", "state", "installed_version",
                                     "author"]))
    elif c == "models":
        dom = []
        if args.custom:
            dom.append(("state", "=", "manual"))
        if args.search:
            dom += ["|", ("model", "ilike", args.search), ("name", "ilike", args.search)]
        rows = o.search_read("ir.model", dom, ["model", "name", "state", "transient"],
                             limit=3000, order="model")
        out(args, rows, table(rows, ["model", "name", "state", "transient"]))
    elif c == "fields":
        f = o.fields(args.model)
        rows = [{"field": k, **v} for k, v in sorted(f.items())]
        if args.required:
            rows = [r for r in rows if r.get("required")]
        if args.custom:
            rows = [r for r in rows if r["field"].startswith("x_")]
        if args.search:
            q = args.search.lower()
            rows = [r for r in rows if q in r["field"] or q in str(r.get("string", "")).lower()]
        for r in rows:
            if r.get("selection"):
                r["selection"] = ",".join(str(s[0]) for s in r["selection"])
        out(args, rows, table(rows, ["field", "type", "string", "required", "readonly",
                                     "store", "relation", "selection"]))
    elif c == "count":
        out(args, o.count(args.model, parse_value(args.domain, [])))
    elif c == "read":
        fields = [x for x in args.fields.split(",") if x] or ["display_name"]
        rows = o.search_read(args.model, parse_value(args.domain, []), fields,
                             limit=args.limit, offset=args.offset, order=args.order)
        out(args, rows, table(rows, ["id"] + fields))
    elif c == "get":
        fields = [x for x in args.fields.split(",") if x]
        out(args, o.execute(args.model, "read", args.ids, fields=fields))
    elif c == "group":
        rows = o.execute(args.model, "read_group", parse_value(args.domain, []),
                         [args.groupby.split(":")[0]], [args.groupby], lazy=True)
        key = args.groupby.split(":")[0]
        for r in rows:
            r["count"] = r.get(f"{key}_count", r.get("__count"))
        rows = sorted(rows, key=lambda r: -(r["count"] or 0))[:args.limit]
        out(args, rows, table(rows, [key, "count"]))
    elif c == "xmlid":
        if len(args.ref) == 2 and args.ref[1].isdigit():
            rows = o.search_read("ir.model.data", [("model", "=", args.ref[0]),
                                                   ("res_id", "=", int(args.ref[1]))],
                                 ["module", "name", "model", "res_id"], limit=20)
        else:
            dom = []
            for r in args.ref:
                mod, _, name = r.partition(".")
                dom = (["|"] + dom if dom else dom) + ["&", ("module", "=", mod),
                                                       ("name", "=", name)]
            rows = o.search_read("ir.model.data", dom, ["module", "name", "model", "res_id"],
                                 limit=100)
        out(args, rows, table(rows, ["module", "name", "model", "res_id"]))
    elif c == "access":
        rows = []
        for m in args.models:
            try:
                rows.append({"model": m, **{op: "yes" if o.can(m, op) else "no"
                                            for op in ("read", "write", "create", "unlink")}})
            except OdooError as e:
                rows.append({"model": m, "read": f"error {e.name}"})
        out(args, rows, table(rows, ["model", "read", "write", "create", "unlink"]))
    elif c == "audit":
        models = args.models.split(",") if args.models else None
        rep = Audit(o, models, args.sample).run()
        md = to_markdown(rep)
        if args.out:
            d = Path(args.out)
            d.mkdir(parents=True, exist_ok=True)
            (d / "audit.json").write_text(dump(rep))
            (d / "audit.md").write_text(md)
            print(f"wrote {d / 'audit.json'} and {d / 'audit.md'}", file=sys.stderr)
        out(args, rep, md)
        return 0
    elif c == "gap":
        spec = parse_value(Path(args.spec).read_text() if args.spec != "-" else "-", {})
        if not isinstance(spec, dict) or not (spec.get("modules") or spec.get("models")):
            raise ValueError("spec needs a non-empty 'modules' or 'models'")
        bad = set(spec) - {"modules", "models"}
        for need in (spec.get("models") or {}).values():
            bad |= set(need) - {"fields", "ops"}
        if bad:
            raise ValueError(f"unknown spec keys: {', '.join(sorted(bad))}")
        g = gap(o, spec)
        out(args, g, gap_markdown(g))
        return 0 if g["ok"] else 3
    elif c == "create":
        vals = parse_value(args.values, None)
        if guard(args, f"create {args.model}", vals):
            out(args, o.execute(args.model, "create", vals))
    elif c == "write":
        ids = [int(x) for x in args.ids.split(",")]
        vals = parse_value(args.values, None)
        if guard(args, f"write {args.model} {ids}", vals):
            out(args, o.execute(args.model, "write", ids, vals))
    elif c == "unlink":
        ids = [int(x) for x in args.ids.split(",")]
        if guard(args, f"unlink {args.model}", ids):
            out(args, o.execute(args.model, "unlink", ids))
    elif c == "call":
        a = parse_value(args.args, [])
        kw = parse_value(args.kwargs, {})
        if args.method in READ_METHODS or guard(
                args, f"call {args.model}.{args.method}", {"args": a, "kwargs": kw}):
            out(args, o.execute(args.model, args.method, *a, **kw))
    return 0


if __name__ == "__main__":
    sys.exit(main())
