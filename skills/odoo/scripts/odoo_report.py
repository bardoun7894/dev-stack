"""Markdown and JSON rendering of an audit report."""
from __future__ import annotations

import json


def to_markdown(rep: dict) -> str:
    s = rep["sections"]
    srv, usr = s.get("server", {}), s.get("user", {})
    lines = [f"# Odoo audit: {srv.get('url')} db `{srv.get('db')}`", "",
             f"- Version: {srv.get('server_version')} (serie {srv.get('server_serie')})",
             f"- Audited as: {usr.get('login')} (uid {usr.get('uid')}, admin: "
             f"{usr.get('admin')})",
             f"- Companies: {', '.join(c['name'] for c in s.get('companies') or []) or '?'}"]
    mods = s.get("modules") or {}
    if mods:
        lines += [f"- Installed modules: {mods.get('installed')}; apps: "
                  f"{', '.join(mods.get('apps', []))}"]
    lines += ["", "## Findings", ""]
    for i, f in enumerate(rep["findings"], 1):
        act = f" -> {f['action']}" if f.get("action") else ""
        lines.append(f"- F{i} [{f['severity']}/{f['kind']}] {f['text']}{act}")
    lines += ["", "## Models", "", "| model | records | read | write | create | unlink |",
              "|---|---|---|---|---|---|"]
    for m in s.get("models", []):
        a = m.get("access", {})
        yn = lambda k: "yes" if a.get(k) is True else ("no" if a.get(k) is False else "?")
        lines.append(f"| {m['model']} | {m.get('count')} | {yn('read')} | {yn('write')} | "
                     f"{yn('create')} | {yn('unlink')} |")
    cust = s.get("custom") or {}
    if cust.get("models") or cust.get("fields"):
        lines += ["", "## Custom models and fields", ""]
        for m in cust.get("models", []):
            lines.append(f"- model `{m['model']}` ({m['name']})")
        for model, fl in (cust.get("fields") or {}).items():
            lines.append(f"- `{model}`: " + ", ".join(f"{f['name']} ({f['type']})" for f in fl))
    if mods.get("third_party"):
        lines += ["", "## Non-Odoo-S.A. modules", ""]
        lines += [f"- {m['name']} ({m['author']}, {m['version']})" for m in mods["third_party"]]
    auto = s.get("automation") or {}
    if auto:
        n = lambda k: "not readable or not installed" if auto.get(k) is None else (
            len(auto[k]) if isinstance(auto[k], list) else auto[k])
        lines += ["", "## Automation", "",
                  f"- Active crons: {n('crons')}",
                  f"- Automated actions (base.automation): {n('automated_actions')}",
                  f"- Python code server actions, standard ones included: "
                  f"{n('server_actions_code')}"]
    lines += ["", "## Health counters", ""]
    lines += [f"- {k}: {v}" for k, v in (s.get("health") or {}).items()]
    return "\n".join(lines) + "\n"


def dump(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str)
