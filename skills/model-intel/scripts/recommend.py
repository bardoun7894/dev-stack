#!/usr/bin/env python3
"""Build data/reachable.json and data/recommendations.md from data/latest.
Usage: recommend.py [--reachable-only]"""
import json, os, re, subprocess, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mi

RULES = json.load(open(mi.SKILL / "config" / "owner_rules.json"))
PI = Path(os.environ.get("MODEL_INTEL_PI_DIR", Path.home() / ".pi/agent"))
PROV_RANK = RULES["provider_rank"]
SUBS = set(RULES["subscription_providers"])


def split_id(full):
    p, _, m = full.partition("/")  # model ids may contain slashes: split on the first only
    return p, m


def mkey(model_id):
    """Normalised join key for a provider model id (last path segment, date suffix dropped)."""
    seg = model_id.split("/")[-1].split(":")[0]
    seg = re.sub(r"-\d{8}$", "", seg)
    return mi.norm(seg)


def build_reachable(tiers_path=None):
    tiers = json.load(open(tiers_path or mi.TIERS))
    metered = set(tiers.get("metered_providers", []))
    blocked = set(tiers.get("_blocked", {}))
    found = {}  # full id -> source

    def add(full, src):
        if full not in blocked:
            found.setdefault(full, src)

    def walk(v):
        if isinstance(v, str) and "/" in v:
            add(v, "tiers.json")
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
    for k in ("tiers", "kinds", "orchestrator"):
        walk(tiers.get(k, {}))
    for f, shape in (("models.json", "providers"), ("models-store.json", None), ("commandcode-models.json", "cc")):
        p = PI / f
        if not p.exists():
            continue
        d = json.load(open(p))
        if shape == "providers":
            for prov, v in d.get("providers", {}).items():
                for m in v.get("models", []):
                    add(f"{prov}/{m['id']}", f)
        elif shape == "cc":
            for m in d.get("models", []):
                add(f"commandcode/{m['id']}", f)
        else:
            for prov, v in d.items():
                for m in v.get("models", []):
                    add(f"{prov}/{m['id']}", f)
    models = {}
    for full, src in found.items():
        prov, mid = split_id(full)
        e = models.setdefault(mkey(mid), {"providers": []})
        e["providers"].append({"provider": prov, "id": full, "subscription": prov in SUBS and prov not in metered,
                               "source": src})
    for e in models.values():
        e["providers"].sort(key=lambda p: (PROV_RANK.index(p["provider"]) if p["provider"] in PROV_RANK else 99, p["id"]))
        e["best_provider"] = e["providers"][0]["provider"]
        e["subscription"] = any(p["subscription"] for p in e["providers"])
    return {"built": mi.today(), "models": models}


def load_llm(reach):
    rows = []
    for r in mi.read_csv(mi.latest_dir() / "llm.csv"):
        idx = mi.num(r["intelligence_index"])
        if idx is None or r["deprecated"] == "y" or r["intelligence_index_estimated"] == "y":
            continue
        key = mi.family_key(r["slug"])
        hit = reach["models"].get(key)
        if hit is None:  # loose match: AA slug often carries a creator prefix, provider ids do not
            for k, v in reach["models"].items():
                if len(k) >= 8 and (key.endswith(k) or k.endswith(key)):
                    hit = v
                    break
        rows.append({"model": r["model"], "base": r["base_model"], "effort": r["effort_mode"], "slug": r["slug"],
                     "key": key, "creator": r["creator"], "index": idx, "cost": mi.num(r["cost_per_task_usd"]),
                     "tps": mi.num(r["output_tokens_per_s"]), "price_in": mi.num(r["price_input_per_1M"]),
                     "price_out": mi.num(r["price_output_per_1M"]), "reach": hit})
    return rows


def reachable_sub(r):
    return r["reach"] is not None and r["reach"]["subscription"]


def allowed(r, use):
    if r["key"] in RULES["never_worker_families"] and use not in ("orchestration", "fallback_claude"):
        return False
    if r["creator"] == "OpenAI" and use not in RULES["openai_only_for"] + ["orchestration"]:
        return False
    return True


EFFORT_RANK = {"non-reasoning": 0, "minimal": 1, "low": 2, "medium": 3, "default": 3, "high": 4, "xhigh": 5, "max": 6}
TOL = RULES.get("effort_tolerance", 1.5)
FLOORS = RULES.get("floors", {})
MIN_TPS = FLOORS.get("min_tps", 100)


def effort_pick(fam, hardest=False):
    """F13: lowest effort whose index is within TOL of the family's xhigh score (best non-max level if no xhigh).
    max is never picked unless the use case is hardest."""
    pool = [r for r in fam if r["effort"] != "max"]
    if hardest or not pool:
        pool = fam if hardest else pool
        return max(pool, key=lambda r: r["index"]) if pool else None
    xh = [r for r in pool if r["effort"] == "xhigh"]
    ref = xh[0]["index"] if xh else max(r["index"] for r in pool)
    ok = [r for r in pool if r["index"] >= ref - TOL]
    return min(ok, key=lambda r: (EFFORT_RANK.get(r["effort"], 3), r["cost"] if r["cost"] is not None else 1e9))


def collapse(rows, use, pred=lambda r: True, hardest=False):
    """One row per reachable subscription family that the owner rules allow for `use`, effort chosen by F13."""
    fams = {}
    for r in rows:
        if reachable_sub(r) and allowed(r, use):
            fams.setdefault(r["key"], []).append(r)
    out = [effort_pick(f, hardest) for f in fams.values()]
    return [r for r in out if r is not None and pred(r)]


def is_hardest(use):
    return use in RULES.get("hardest_use_cases", [])


def quality(rows, use, pred=lambda r: True, tie=1.0):
    """Quality-first: highest index among reachable subscription models (quota is the constraint, not dollars);
    within `tie` points of the top, the cheaper wins."""
    c = collapse(rows, use, pred, is_hardest(use))
    if not c:
        return None
    top = max(r["index"] for r in c)
    near = [r for r in c if r["index"] >= top - tie]
    return min(near, key=lambda r: (r["cost"] if r["cost"] is not None else 1e9, -r["index"]))


def value(rows, use, floor):
    """Value-first: best index per cost-per-task above the floor; prefer >= MIN_TPS tok/s."""
    c = [r for r in collapse(rows, use, hardest=is_hardest(use)) if r["index"] >= floor and r["cost"]]
    fast = [r for r in c if r["tps"] and r["tps"] >= MIN_TPS]
    c = fast or c
    return max(c, key=lambda r: (r["index"] / r["cost"], r["index"])) if c else None


def cheapest(rows, use, floor, need_tps=True):
    c = [r for r in collapse(rows, use, hardest=is_hardest(use)) if r["index"] >= floor and r["cost"] is not None
         and (not need_tps or (r["tps"] and r["tps"] >= MIN_TPS))]
    return min(c, key=lambda r: (r["cost"], -r["index"])) if c else None


def find_pin(rows, pin, rule_effort=None):
    """Row for an owner pin ({model, effort?}); without an explicit effort the F13 rule picks it."""
    fam = [r for r in rows if r["base"].lower() == pin["model"].lower() and r["cost"] is not None]
    if not fam:
        return None
    if pin.get("effort"):
        hit = [r for r in fam if r["effort"] == pin["effort"]]
        return hit[0] if hit else None
    return effort_pick(fam)


def candidate(rows, use, pin_row, hardest=False):
    """A reachable subscription model that beats the pin by more than the noise margin (report only)."""
    if pin_row is None:
        return None
    best = [r for r in collapse(rows, use, hardest=hardest) if r["key"] != pin_row["key"]]
    best = [r for r in best if r["index"] >= pin_row["index"] + RULES.get("candidate_margin", 1.0)]
    return max(best, key=lambda r: r["index"]) if best else None


def fmt(r, note=""):
    if r is None:
        return f"| none reachable | | | | | | {note} |"
    cost = "n/a" if r["cost"] is None else f"${r['cost']:.3f}"
    tps = "n/a" if not r["tps"] else f"{r['tps']:.0f}"
    prov = r["reach"]["best_provider"] if r["reach"] else "not reachable"
    return f"| {r['base']} | {r['effort']} | {r['index']:.1f} | {cost} | {tps} | {prov} | {note} |"


def _short(r):
    return f"{r['base']} {r['effort']} {r['index']:.1f}" + ("" if r["cost"] is None else f" at ${r['cost']:.2f}")


def pin_note(rows, use, pin_row, label):
    """Note for an owner-pinned row: the pin itself, a better candidate, and what F13 alone would pick."""
    bits = [label]
    if pin_row is not None:
        fam = [r for r in rows if r["key"] == pin_row["key"] and r["cost"] is not None]
        rule = effort_pick(fam)
        if rule is not None and rule["effort"] != pin_row["effort"] and abs(rule["index"] - pin_row["index"]) > 0.25:
            bits.append(f"F13 alone would pick {rule['effort']} {rule['index']:.1f} at ${rule['cost']:.2f}")
        cand = candidate(rows, use, pin_row, is_hardest(use))
        if cand is not None:
            bits.append(f"candidate (not applied): {_short(cand)}")
    return "; ".join(bits)


def usecases(rows):
    """[(name, use, row, objective, note)]"""
    pins = RULES["use_case_pins"]
    oa = lambda r: r["creator"] == "OpenAI"
    notclaude = lambda r: r["creator"] != "Anthropic"
    out = []
    orch = find_pin(rows, pins["orchestration"])
    out.append(("Orchestration", "orchestration", orch, "quality-first, owner pin",
                pin_note(rows, "orchestration", orch, "owner pin: Opus 5.5 high")))
    arch = find_pin(rows, pins["architecture"])
    out.append(("Architecture", "orchestration", arch, "quality-first, owner pin",
                pin_note(rows, "orchestration", arch, "owner pin: Opus 5.5 xhigh")
                if arch else "owner pin: Opus 5.5 xhigh; no AA xhigh score in this snapshot"))
    main = find_pin(rows, pins["main_coding"])
    out.append(("Main coding", "code", main, "quality-first, owner pin", pin_note(rows, "code", main, "owner pin: Opus 5.5 high")))
    rev = quality(rows, "review", oa)
    cand = candidate(rows, "review", rev, is_hardest("review"))
    out.append(("Plans / review / second opinion", "review", rev, "quality-first, GPT for review (owner)",
                "highest-index GPT reachable" + (f"; candidate (not applied): {_short(cand)}" if cand else "")))
    out.append(("Search subagents", "search", value(rows, "search", FLOORS.get("search", 33)),
                f"value-first: index/cost, index >= {FLOORS.get('search', 33)}, >= {MIN_TPS} tok/s", ""))
    jud = find_pin(rows, pins["judge"])
    cheap = cheapest(rows, "judge", FLOORS.get("judge", 40))
    jnote = "owner pin: Jev first, Haiku 5.5 fallback"
    if cheap is not None and (jud is None or cheap["key"] != jud["key"]):
        jnote += f"; candidate (not applied): {_short(cheap)}"
    out.append(("Judging subagents", "judge", jud, "owner pin: Jev first, Haiku 5.5 fallback", jnote))
    out.append(("Bulk cheap text", "bulk", value(rows, "bulk", FLOORS.get("bulk", 30)),
                f"value-first: index/cost, index >= {FLOORS.get('bulk', 30)}, >= {MIN_TPS} tok/s", ""))
    out.append(("Non-Claude fallback", "fallback",
                _fallback(rows),
                f"index/cost among non-Claude subscription models, index >= {FLOORS.get('fallback', 44)}", ""))
    first = find_pin(rows, pins["arabic_first"])
    out.append(("Arabic copy (GPT first)", "language", first, "quality-first, owner pin (rule, not measurement)",
                "owner rule 2026-10-11; weakest evidence"))
    fb = find_pin(rows, pins["arabic_fallback"])
    out.append(("Arabic copy (Gemini fallback)", "language", fb, "owner pin (fallback)", "owner rule 2026-10-11"))
    return out


def _fallback(rows):
    c = [r for r in collapse(rows, "fallback", lambda r: r["creator"] != "Anthropic", is_hardest("fallback"))
         if r["index"] >= FLOORS.get("fallback", 44) and r["cost"]]
    return max(c, key=lambda r: (r["index"] / r["cost"], r["index"])) if c else None


def ladder(rows, key):
    fam = [r for r in rows if r["key"] == key and r["cost"] is not None]
    fam.sort(key=lambda r: mi.EFFORT_ORDER.index(r["effort"]) if r["effort"] in mi.EFFORT_ORDER else 99)
    # order by cost so the ladder always climbs
    fam.sort(key=lambda r: r["cost"])
    out, stop_marked = [], False
    knee = RULES["knee_points_per_dollar"]
    for i, r in enumerate(fam):
        note = ""
        if i:
            p = fam[i - 1]
            dc, di = r["cost"] - p["cost"], r["index"] - p["index"]
            gain = f"{di / dc:+.1f}" if dc > 1e-9 else "n/a"
            if not stop_marked and (di <= 0 or (dc > 1e-9 and di / dc < knee)):
                out[-1][-1] = "**best value: stop here**"
                stop_marked = True
        else:
            gain = ""
        out.append([r["effort"], f"{r['index']:.1f}", f"${r['cost']:.3f}", "n/a" if not r["tps"] else f"{r['tps']:.0f}", gain, note])
    pick = effort_pick(fam)
    for row, r in zip(out, fam):
        if pick is not None and r is pick:
            row[-1] = (row[-1] + " " if row[-1] else "") + "**F13 pick**"
    return out


def media_tables():
    L = []
    titles = [("media_text_to_image", "Image (text-to-image)"), ("media_image_editing", "Image editing"),
              ("media_text_to_video", "Video (text-to-video)"), ("media_image_to_video", "Video (image-to-video)"),
              ("media_tts", "TTS"), ("media_stt", "STT (lower WER is better)")]
    for f, title in titles:
        p = mi.latest_dir() / (f + ".csv")
        if not p.exists():
            continue
        rows = mi.read_csv(p)[:5]
        L += [f"### {title}", "", "| # | Model | Creator | Score | Price | Unit |", "|---|---|---|---|---|---|"]
        for r in rows:
            L.append(f"| {r['rank']} | {r['model']} | {r['creator']} | {r['score']} | {r['price'] or 'n/a'} | {r['price_unit']} |")
        L.append("")
    return L


def pixverse_note():
    out = []
    for f in ("media_text_to_video", "media_image_to_video"):
        rows = mi.read_csv(mi.latest_dir() / (f + ".csv"))
        pix = next((r for r in rows if "pixverse" in (r["model"] + r["creator"]).lower()), None)
        if pix:
            better = [r for r in rows if mi.num(r["score"]) > mi.num(pix["score"])]
            out.append(f"{f.replace('media_', '')}: PixVerse {pix['model']} ranks #{pix['rank']} (elo {pix['score']}, "
                       f"{pix['price'] or 'n/a'} {pix['price_unit']}); {len(better)} models score higher"
                       + (f", best: {better[0]['model']} (elo {better[0]['score']}, {better[0]['price'] or 'n/a'})" if better else ""))
        else:
            out.append(f"{f.replace('media_', '')}: PixVerse not on this leaderboard; top is {rows[0]['model']} (elo {rows[0]['score']})")
    return out


KIE_SCRIPT = Path(os.path.expanduser(os.environ.get("MODEL_INTEL_KIE_SCRIPT", RULES.get("kie", {}).get("script", "~/.claude/skills/kie-ai/scripts/kie.py"))))
KIE_EXTRA_DOC = Path(os.environ.get("MODEL_INTEL_KIE_DOC", Path.home() / "projects/HighlighterAllepo/.claude/skills/kie-models/references/en.md"))

# AA display name (lower-case regex) -> Kie id regex. Match on version: a newer AA model than Kie lists is NOT on Kie.
KIE_ALIASES = [
    (r"seedance 2\.5", r"^bytedance/seedance-2-5$"),
    (r"seedance 2\.0", r"^bytedance/seedance-2$"),
    (r"seedance 1\.5", r"^bytedance/seedance-1-5-pro$"),
    (r"kling (3\.0|v3|3)\b", r"^kling/(kling-3-0|v3-turbo-)"),
    (r"kling 2\.5", r"^kling/v25-turbo-"),
    (r"kling 2\.1", r"^kling/v2-1-"),
    (r"hailuo 2\.3", r"^hailuo/2-3-"),
    (r"hailuo 0?2\b", r"^hailuo/02-"),
    (r"minimax h3", r"^minimax-h3/"),
    (r"wan ?2\.7", r"^wan/2-7-"),
    (r"wan ?2\.6", r"^wan/2-6-"),
    (r"wan ?2\.5", r"^wan/2-5-"),
    (r"wan ?2\.2", r"^wan/2-2-"),
    (r"pixverse", r"^pixverse/"),
    (r"veo 3\.1", r"^veo-3-1$"),
    (r"happyhorse-1\.1", r"^happyhorse-1-1/"),
    (r"happyhorse-1\.0", r"^happyhorse/"),
    (r"grok imagine video", r"^grok-imagine/(text|image)-to-video$"),
    (r"grok imagine image", r"^grok-imagine/(text|image)-to-image$"),
    (r"gemini omni", r"^gemini-omni-video$"),
    (r"nano banana pro", r"^google/pro-image-to-image$"),
    (r"nano banana 2(?![.\d])", r"^google/nanobanana2$"),
    (r"nano banana(?! pro| ?2)", r"^google/nano-banana(-edit)?$"),
    (r"seedream 5\.0 pro", r"^seedream/5-pro-"),
    (r"seedream 5\.0 lite", r"^seedream(/5-lite-|-5-lite-)"),
    (r"seedream 4\.5", r"^seedream/4-5-"),
    (r"seedream 4(?![.\d])", r"^seedream/seedream-v4-"),
    (r"gpt image 1\.5", r"^gpt-image/1-5-"),
    (r"gpt image 2(?![.\d])", r"^gpt/gpt-image-2-"),
    (r"imagen 4", r"^google/imagen4"),
    (r"flux 2", r"^flux2/"),
    (r"ideogram v3", r"^ideogram/v3-"),
    (r"eleven.*\bv3\b", r"^elevenlabs/text-to-dialogue-v3$"),
    (r"eleven.*turbo.*2\.5", r"^elevenlabs/text-to-speech-turbo-2-5$"),
    (r"eleven.*multilingual.*v2", r"^elevenlabs/text-to-speech-multilingual-v2$"),
    (r"gemini 3\.1 flash tts", r"^google/gemini-3-1-flash-tts$"),
]


def build_kie():
    """data/kie_models.json from kie.py `models` (the kie-ai skill catalogue), plus ids named in the kie-models skill doc."""
    ids, source = [], []
    if KIE_SCRIPT.exists():
        r = subprocess.run([sys.executable, "-I", str(KIE_SCRIPT), "models"], capture_output=True, text=True, timeout=30)
        ids = [l.strip() for l in r.stdout.splitlines() if l.startswith("  ") and l.strip()]
        source.append(f"{KIE_SCRIPT} models")
    if not ids:
        md = KIE_SCRIPT.parent.parent / "references" / "models.md"
        if md.exists():
            for line in md.read_text().splitlines():
                if line.startswith("`") and line.endswith("`"):
                    ids += [t.strip(" `") for t in line.split("·")]
            source.append(str(md))
    if KIE_EXTRA_DOC.exists():
        doc = KIE_EXTRA_DOC.read_text()
        extra = set(re.findall(r"api/v1/models/([a-z0-9][a-z0-9./-]*?)/(?:price|schema|success-rate)", doc))
        extra |= set(re.findall(r'"model":\s*"([a-z0-9][a-z0-9./-]*)"', doc))
        ids += sorted(extra)
        source.append(f"{KIE_EXTRA_DOC} (example ids)")
    return {"built": mi.today(), "catalogue_date": RULES.get("kie", {}).get("catalogue_date", ""),
            "source": source, "ids": sorted(set(ids))}


def load_kie():
    p = mi.DATA / "kie_models.json"
    if p.exists():
        return json.load(open(p))
    k = build_kie()
    if k["ids"]:
        mi.DATA.mkdir(parents=True, exist_ok=True)
        json.dump(k, open(p, "w"), indent=1)
    return k


def kie_ids(name, kie):
    """Kie ids an AA display name maps to (empty = not on Kie)."""
    n = name.lower()
    hits = []
    for name_re, id_re in KIE_ALIASES:
        if re.search(name_re, n):
            hits += [i for i in kie["ids"] if re.search(id_re, i)]
    return sorted(set(hits))


def _elo(r):
    if r.get("score_kind") == "wer":
        return f"WER {mi.num(r['score']):.4f} (#{r['rank']})"
    return f"elo {mi.num(r['score']):.0f} (#{r['rank']})"


def media_rows(kie):
    """Per media use case: best model reachable on Kie and, separately, the global leader (not on Kie).
    -> [(use case, row, kie ids, note)]"""
    d = mi.latest_dir()
    out = []
    t2v = mi.read_csv(d / "media_text_to_video.csv")
    pix = next((r for r in t2v if "pixverse" in (r["model"] + r["creator"]).lower()), None)
    if pix:
        out.append(("Video MarktingTeam (owner pin)", pix, kie_ids(pix["model"], kie), "PixVerse stays; pin is never auto-changed"))
    for f, name in (("media_text_to_video.csv", "Video text-to-video"), ("media_image_to_video.csv", "Video image-to-video"),
                    ("media_text_to_image.csv", "Image text-to-image"), ("media_image_editing.csv", "Image editing"),
                    ("media_tts.csv", "TTS"), ("media_stt.csv", "STT (lower WER first)")):
        p = d / f
        if not p.exists():
            continue
        rows = sorted((r for r in mi.read_csv(p) if (r.get("rank") or "").isdigit()), key=lambda r: int(r["rank"]))
        if not rows:
            continue
        on = [(r, kie_ids(r["model"], kie)) for r in rows]
        on = [(r, ids) for r, ids in on if ids]
        note = "Arabic text = overlay, not model-rendered" if name.startswith("Image text") else ""
        if on:
            out.append((f"{name}: best on Kie", on[0][0], on[0][1], note))
        else:
            out.append((f"{name}: best on Kie", None, [], "nothing on the leaderboard maps to a Kie model"))
        lead = rows[0]
        if not kie_ids(lead["model"], kie):
            out.append((f"{name}: global leader (not on Kie)", lead, [], "not on Kie: report only"))
    return out


def render(reach):
    rows = load_llm(reach)
    cur = mi.latest_dir()
    L = [f"# Model recommendations ({cur.name})", "",
         "Source: Artificial Analysis snapshot + reachable.json. Index = AA Intelligence Index; cost = AA cost per task (USD); "
         "providers listed best-first (subscriptions before openrouter).", "",
         "## Use cases", "",
         "Claude and GPT are subscriptions: the constraint is quota, not dollars. Efforts follow F13 (lowest effort within "
         f"{TOL} pts of the model's xhigh; never max unless a use case is marked hardest). Index differences under ~1 point are noise.", "",
         "| Use case | Model | Effort | Index | Cost/task | tok/s | Via | Note |", "|---|---|---|---|---|---|---|---|"]
    for name, _, r, why, note in usecases(rows):
        L.append(f"| {name} | " + fmt(r, note)[2:])
    kie = load_kie()
    for name, r, ids, note in media_rows(kie):
        if r is None:
            L.append(f"| {name} | none | n/a | n/a | n/a | n/a | n/a | {note} |")
            continue
        price = f"{r['price'] or 'n/a'} {r['price_unit']}"
        via = "Kie: " + ", ".join(ids[:3]) if ids else "not on Kie"
        L.append(f"| {name} | {r['model']} ({r['creator']}) | n/a | {_elo(r)} | {price} | n/a | {via} | {note} |")
    L += ["", f"Kie catalogue: {len(kie['ids'])} ids (kie-ai skill catalogue dated {kie.get('catalogue_date') or 'unknown'}; "
          "newer Kie models may be missing, check kie.ai/market).", "",
          "Objectives: " + "; ".join(f"{n}: {w}" for n, _, _, w, _ in usecases(rows)), "",
          "## Owner rules", "",
          "- Arabic copy: GPT first, Gemini fallback (owner rule 2026-10-11, not a measurement; weakest evidence).",
          "- Main coding and orchestration are pinned to Opus 5.5 high (architecture xhigh); a better model is shown as a candidate and never replaces the pin. Recommendation only: tiers.json is not written here.", "- MarktingTeam video stays PixVerse (owner rule); better options below are reported only, never auto-applied.",
          "- Arabic text in images is added as an overlay, never rendered by the image model.", "",
          "## Effort ladders (reachable families)", "",
          f"Gain = index points per extra dollar vs the previous level; stop where it falls under {RULES['knee_points_per_dollar']} pts/$.", ""]
    fams = {}
    for r in rows:
        if reachable_sub(r) and r["cost"] is not None:
            fams.setdefault(r["key"], []).append(r)
    ranked = sorted(fams.items(), key=lambda kv: -max(x["index"] for x in kv[1]))
    for key, fr in ranked:
        if len(fr) < 2:
            continue
        L += [f"### {fr[0]['base']}", "", "| Effort | Index | Cost/task | tok/s | Gain per $ | |", "|---|---|---|---|---|---|"]
        for row in ladder(rows, key):
            L.append("| " + " | ".join(row) + " |")
        L.append("")
    L += ["## Media leaderboards (top 5)", ""] + media_tables()
    L += ["## MarktingTeam video check", ""] + [f"- {x}" for x in pixverse_note()] + [""]
    unreach = sorted((r for r in rows if r["reach"] is None and r["effort"] in ("max", "default", "xhigh", "high")),
                     key=lambda r: -r["index"])[:8]
    L += ["## Best models not reachable today", "", "| Model | Effort | Index | Cost/task |", "|---|---|---|---|"]
    for r in unreach:
        L.append(f"| {r['base']} | {r['effort']} | {r['index']:.1f} | {'n/a' if r['cost'] is None else '$%.3f' % r['cost']} |")
    return "\n".join(L) + "\n"


def main(argv):
    reach = build_reachable()
    mi.DATA.mkdir(parents=True, exist_ok=True)
    json.dump(reach, open(mi.DATA / "reachable.json", "w"), indent=1)
    kie = build_kie()
    if kie["ids"]:
        json.dump(kie, open(mi.DATA / "kie_models.json", "w"), indent=1)
    if "--reachable-only" in argv:
        return 0
    if mi.latest_dir() is None:
        print("recommend: no snapshot yet, run fetch.py", file=sys.stderr)
        return 1
    (mi.DATA / "recommendations.md").write_text(render(reach))
    print(mi.DATA / "recommendations.md")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
