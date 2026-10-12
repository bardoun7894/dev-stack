#!/usr/bin/env python3
"""Render ~/.claude/reference/model-picks.md from the model-intel data (stdlib, no network, no LLM).
Reuses recommend.py (usecases, ladders, media rows) and config/owner_rules.json.
Env: MODEL_PICKS_OUT overrides the output path. Atomic write; on any error the old file stays and exit is 1."""
import json, os, re, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mi
import recommend

OUT_DEFAULT = Path.home() / ".claude/reference/model-picks.md"
ARTIFACT_DEFAULT = "https://claude.ai/artifact/Ccvh322zK2mfMmFLT6kkDV"
LADDER_FAMILIES = ["Claude Opus 5.5", "Claude Sonnet 5.5", "Claude Haiku 5.5", "GPT-6.1 Sol"]
LADDER_EFFORTS = ["low", "medium", "high", "xhigh", "max"]
JUDGE_LABEL = "Jev first (score/noul/choice, ~$0.00002); Haiku 5.5 only on Jev exit 2/3 or low confidence"


def short(name):
    return name[len("Claude "):] if name.startswith("Claude ") else name


def cost(r):
    return "n/a" if r is None or r["cost"] is None else f"${r['cost']:.2f}"


def use_row(label, r, model=None):
    if r is None:
        return f"| {label} | {model or 'none reachable'} | n/a | n/a | n/a |"
    return f"| {label} | {model or short(r['base'])} | {r['effort']} | {r['index']:.1f} | {cost(r)} |"


def fam_rows(rows, base):
    return {r["effort"]: r for r in rows if r["base"] == base and r["cost"] is not None}


def lookup(rows, base, effort):
    return fam_rows(rows, base).get(effort)


def artifact_link(path):
    try:
        m = re.search(r"https://claude\.ai/artifact/\S+", Path(path).read_text())
        if m:
            return m.group(0)
    except OSError:
        pass
    return ARTIFACT_DEFAULT


def use_table(rows):
    uc = {name: r for name, _, r, _, _ in recommend.usecases(rows)}
    L = ["| Use | Model | Effort | Index | Cost/task |", "|---|---|---|---|---|",
         use_row("Orchestration", uc["Orchestration"]),
         use_row("Architecture", uc["Architecture"]),
         use_row("Main coding", uc["Main coding"]),
         use_row("Review, second opinion", uc["Plans / review / second opinion"]),
         use_row("Search subagents", uc["Search subagents"]),
         use_row("Judging", uc["Judging subagents"], JUDGE_LABEL),
         use_row("Bulk cheap text", uc["Bulk cheap text"]),
         use_row("Non-Claude fallback (OpenCode Go)", uc["Non-Claude fallback"]),
         use_row("Arabic copy, first (owner rule)", uc["Arabic copy (GPT first)"]),
         use_row("Arabic copy, fallback (owner rule)", uc["Arabic copy (Gemini fallback)"])]
    return L


def effort_section(rows):
    tol = recommend.TOL
    steps = []
    for base in LADDER_FAMILIES:
        xh, mx = lookup(rows, base, "xhigh"), lookup(rows, base, "max")
        if xh and mx:
            steps.append(f"{mx['index'] - xh['index']:.1f} for +${mx['cost'] - xh['cost']:.2f} on {short(base).split(' ')[0] if base.startswith('Claude ') else base}")
    L = ["## Effort rule", "",
         f"- Pick the lowest effort within {tol:g} index points of the model's xhigh. Never max.",
         "- xhigh is the practical ceiling (F6)." + (" xhigh to max adds " + ", ".join(steps) + "." if steps else "")
         + " Max runs also take 290 to 670 s end to end.", "",
         "Effort ladders, index / cost per task USD:", ""]
    fams = [b for b in LADDER_FAMILIES if fam_rows(rows, b)]
    if fams:
        L += ["| Effort | " + " | ".join(short(b) for b in fams) + " |", "|---|" + "---|" * len(fams)]
        for e in LADDER_EFFORTS:
            cells = []
            for b in fams:
                r = fam_rows(rows, b).get(e)
                cells.append("n/a" if r is None else f"{r['index']:.1f} / {r['cost']:.2f}" if r["cost"] >= 0.1
                             else f"{r['index']:.1f} / {r['cost']:.3f}")
            L.append(f"| {e} | " + " | ".join(cells) + " |")
    return L


def rules_section(rows):
    opus, sonnet = lookup(rows, "Claude Opus 5.5", "high"), lookup(rows, "Claude Sonnet 5.5", "xhigh")
    L = ["## Rules", "",
         "- Subscriptions first (" + ", ".join(recommend.RULES["subscription_providers"][:4]) + "); OpenRouter last.",
         "- Fable is not used: below Opus 5.5 at every level for 1.3x to 4.3x the cost per task."]
    if opus and sonnet:
        L += [f"- Opus high beats Sonnet xhigh on quality and cost (F1): {opus['index']:.1f} at {cost(opus)} against "
              f"{sonnet['index']:.1f} at {cost(sonnet)}.", "  Sonnet's edge is output speed only."]
    L += ["- Sol high is the best-value reasoning tier but slow (50 tok/s, 70 s end to end).",
          "- Open models fit as implementers under a stronger planner; agentic tool calling still lags Opus.",
          "  Good value: MiMo-V2.6-Pro, GLM-5.3-Flash, DeepSeek V4.1 Flash. Poor value: GLM-5.3 max, Kimi K3."]
    return L


def media_section(kie):
    L = ["## Media", "", "| Task | Pick | Notes |", "|---|---|---|"]
    for name, r, ids, note in recommend.media_rows(kie):
        if r is None:
            L.append(f"| {name} | none | {note} |")
            continue
        price = f"{r['price'] or 'n/a'} {r['price_unit']}"
        via = "Kie: " + ", ".join(ids[:2]) if ids else "not on Kie"
        extra = f"; {note}" if note and note not in ("not on Kie: report only",) else ""
        L.append(f"| {name} | {r['model']} ({r['creator']}) | {recommend._elo(r)}, {price}; {via}{extra} |")
    L.append("| Arabic text in images | Overlay in post | Generate without text, overlay with a real font. Unmeasured. |")
    L += ["", "The Kie column may lag the live catalog. Test a short Arabic voice sample before a production run."]
    return L


def build(reach, out_path):
    cur = mi.latest_dir()
    if cur is None:
        raise RuntimeError("no snapshot yet, run fetch.py")
    rows = recommend.load_llm(reach)
    if not rows:
        raise RuntimeError("no LLM rows in latest snapshot")
    L = ["# Model picks", "",
         f"Snapshot {cur.name}, source artificialanalysis.ai. Generated by model-intel (weekly). Do not edit by hand. "
         f"Full page: {artifact_link(out_path)}", "",
         "Index is the AA Intelligence Index; cost is AA cost per task in USD. Differences under about 1 point are noise.", "",
         "## Use -> model, effort, index, cost/task", ""]
    L += use_table(rows)
    L += ["", "Arabic is an owner rule, not a measurement. No benchmark covers Arabic.",
          "Opus orchestration, architecture and main coding are owner pins.", ""]
    L += effort_section(rows) + [""]
    L += rules_section(rows) + [""]
    L += media_section(recommend.load_kie()) + [""]
    L += ["## Pointer", "",
          "Router chains live in ~/.config/jev-router/tiers.json; detail in the skill's data/recommendations.md; "
          "KB detail in dev-stack ai-knowledge-base concepts model-selection-2026-10, open-models-value-2026-10, "
          "media-models-2026-10, arabic-model-choice."]
    return "\n".join(L) + "\n"


def main():
    out = Path(os.environ.get("MODEL_PICKS_OUT") or OUT_DEFAULT)
    tmp = None
    try:
        rp = mi.DATA / "reachable.json"
        reach = json.load(open(rp)) if rp.exists() else recommend.build_reachable()
        text = build(reach, out)
        out.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".model-picks.", suffix=".tmp", dir=out.parent)
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, out)
        tmp = None
        print(out)
        return 0
    except Exception as e:  # keep the old file, report, fail
        print(f"render_picks: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(main())
