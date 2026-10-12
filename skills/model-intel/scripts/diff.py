#!/usr/bin/env python3
"""Compare latest snapshot vs the previous one: new / removed models, index, price, speed changes > 5%.
Usage: diff.py [--json]   Prints markdown (or JSON with --json). Exit 0 always (no previous = note only)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mi

THRESH = 0.05
MEDIA_ELO_STEP = 20.0


def rel(a, b):
    return None if a is None or b is None or a == 0 else (b - a) / abs(a)


def diff_llm(old_rows, new_rows):
    old = {r["slug"]: r for r in old_rows}
    new = {r["slug"]: r for r in new_rows}
    res = {"new": [], "removed": [], "changed": []}
    for s, r in new.items():
        if s not in old:
            res["new"].append({"slug": s, "model": r["model"], "index": mi.num(r["intelligence_index"]),
                               "cost": mi.num(r["cost_per_task_usd"]), "tps": mi.num(r["output_tokens_per_s"])})
    for s, r in old.items():
        if s not in new:
            res["removed"].append({"slug": s, "model": r["model"]})
    fields = [("intelligence_index", "index"), ("cost_per_task_usd", "cost/task"),
              ("blended_price_3to1_per_1M", "price"), ("output_tokens_per_s", "tok/s")]
    for s, r in new.items():
        if s not in old:
            continue
        for col, label in fields:
            a, b = mi.num(old[s][col]), mi.num(r[col])
            d = rel(a, b)
            if d is not None and abs(d) > THRESH:
                res["changed"].append({"slug": s, "model": r["model"], "field": label, "old": a, "new": b, "pct": round(d * 100, 1)})
    return res


def diff_media(old_rows, new_rows):
    old = {r["model"]: r for r in old_rows}
    new = {r["model"]: r for r in new_rows}
    res = {"new": [m for m in new if m not in old], "removed": [m for m in old if m not in new], "changed": []}
    for m, r in new.items():
        if m in old:
            a, b = mi.num(old[m]["score"]), mi.num(r["score"])
            if a is not None and b is not None and abs(b - a) >= (MEDIA_ELO_STEP if r["score_kind"] == "elo" else 0.005):
                res["changed"].append({"model": m, "old": a, "new": b})
            pa, pb = mi.num(old[m]["price"]), mi.num(r["price"])
            d = rel(pa, pb)
            if d is not None and abs(d) > THRESH:
                res["changed"].append({"model": m, "field": "price", "old": pa, "new": pb})
    top_old = old_rows[0]["model"] if old_rows else None
    top_new = new_rows[0]["model"] if new_rows else None
    res["top_changed"] = [top_old, top_new] if top_old != top_new else None
    return res


def compute(prev, cur):
    out = {"previous": prev.name, "latest": cur.name, "llm": diff_llm(mi.read_csv(prev / "llm.csv"), mi.read_csv(cur / "llm.csv")), "media": {}}
    for f in mi.MEDIA_FILES:
        if (prev / f).exists() and (cur / f).exists():
            out["media"][f[:-4]] = diff_media(mi.read_csv(prev / f), mi.read_csv(cur / f))
    return out


def render(d):
    L = [f"# Model changes {d['previous']} -> {d['latest']}", ""]
    llm = d["llm"]
    L.append(f"## LLM: {len(llm['new'])} new, {len(llm['removed'])} removed, {len(llm['changed'])} changed >5%")
    for n in sorted(llm["new"], key=lambda x: -(x["index"] or 0))[:25]:
        L.append(f"- NEW {n['model']} index {n['index']} cost/task {n['cost']} tok/s {n['tps']}")
    for n in llm["removed"][:25]:
        L.append(f"- REMOVED {n['model']}")
    for c in sorted(llm["changed"], key=lambda x: -abs(x["pct"]))[:40]:
        L.append(f"- {c['model']}: {c['field']} {c['old']:.4g} -> {c['new']:.4g} ({c['pct']:+.1f}%)")
    for cat, m in d["media"].items():
        L += ["", f"## {cat}: {len(m['new'])} new, {len(m['removed'])} removed, {len(m['changed'])} changed"]
        if m["top_changed"]:
            L.append(f"- TOP CHANGED: {m['top_changed'][0]} -> {m['top_changed'][1]}")
        for n in m["new"][:10]:
            L.append(f"- NEW {n}")
        for n in m["removed"][:10]:
            L.append(f"- REMOVED {n}")
    return "\n".join(L) + "\n"


def main(argv):
    cur, prev = mi.latest_dir(), mi.previous_dir()
    if cur is None or prev is None:
        print("# Model changes\n\nNo previous snapshot to compare against yet.")
        return 0
    d = compute(prev, cur)
    print(json.dumps(d, indent=1) if "--json" in argv else render(d), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
