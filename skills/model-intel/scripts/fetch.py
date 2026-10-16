#!/usr/bin/env python3
"""Fetch Artificial Analysis LLM + media leaderboards into data/snapshots/DATE/ and point data/latest at it.

Exit 0 ok, 1 fetch/parse failed or row counts dropped >30% (previous latest kept).
Usage: fetch.py [--from-dir DIR]   (DIR holds saved pages named like PAGES below; used by tests and seeding)
Env: AA_API_KEY (official API first, falls back to the public pages), MODEL_INTEL_DATA, MODEL_INTEL_DATE.
"""
import json, os, re, shutil, sys, urllib.request
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mi

BASE = "https://artificialanalysis.ai"
API = BASE + "/api/v2"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15"
# file name in --from-dir -> (url path, output csv)
PAGES = {
    "llm.html": ("/leaderboards/models", "llm.csv"),
    "text-to-image.html": ("/image/leaderboard/text-to-image", "media_text_to_image.csv"),
    "image-editing.html": ("/image/leaderboard/editing", "media_image_editing.csv"),
    "text-to-video.html": ("/video/leaderboard/text-to-video", "media_text_to_video.csv"),
    "image-to-video.html": ("/video/leaderboard/image-to-video", "media_image_to_video.csv"),
    "tts.html": ("/text-to-speech/leaderboard/provider-voice", "media_tts.csv"),
    "stt.html": ("/speech-to-text", "media_stt.csv"),
}
EFFORT_NAMES = {"max", "xhigh", "high", "medium", "low", "minimal", "non-reasoning"}


def iter_objs(txt, must):
    dec = json.JSONDecoder()
    for m in re.finditer(r'\{"', txt):
        try:
            o, _ = dec.raw_decode(txt[m.start():])
        except ValueError:
            continue
        if isinstance(o, dict) and must in o:
            yield o


def iter_arrays(txt):
    dec = json.JSONDecoder()
    for m in re.finditer(r'"([A-Za-z0-9_]+)":\[\{"', txt):
        try:
            arr, _ = dec.raw_decode(txt[m.end() - 3:])
        except ValueError:
            continue
        if isinstance(arr, list) and arr and isinstance(arr[0], dict):
            yield m.group(1), arr


def effort_of(name):
    paren = re.search(r"\(([^)]*)\)\s*$", name)
    if paren:
        for part in [p.strip().lower() for p in paren.group(1).split(",")]:
            if part in EFFORT_NAMES:
                return part
            if part.endswith(" max") or part.endswith(", max"):
                return "max"
        if "non-reasoning" in paren.group(1).lower():
            return "non-reasoning"
    return "default"


def base_of(name):
    return re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()


def parse_llm(html):
    txt = mi.rsc_text(html)
    rel = {}
    for o in iter_objs(txt, "releaseDate"):
        if "slug" in o:
            rel[o["slug"]] = o["releaseDate"]
    rows, seen = [], set()
    for o in iter_objs(txt, "intelligenceIndex"):
        slug = o.get("slug")
        if not slug or "name" not in o or (slug, effort_of(o["name"])) in seen:
            continue
        seen.add((slug, effort_of(o["name"])))
        pin, pout = o.get("price1mInputTokens"), o.get("price1mOutputTokens")
        blended = round((3 * pin + pout) / 4, 4) if pin is not None and pout is not None else ""

        def g(k):
            v = o.get(k)
            return "" if v is None else v
        yn = lambda b: "y" if b else "n"
        name = o["name"]
        rows.append({
            "model": name, "base_model": base_of(name), "effort_mode": effort_of(name), "slug": slug,
            "creator": o.get("modelCreatorName", ""), "open_weights": yn(o.get("isOpenWeights")),
            "reasoning": yn(o.get("isReasoning")), "deprecated": yn(o.get("deprecated")),
            "intelligence_index": g("intelligenceIndex") if g("intelligenceIndex") == "" else round(o["intelligenceIndex"], 2),
            "intelligence_index_estimated": yn(o.get("intelligenceIndexIsEstimated")),
            "cost_per_task_usd": g("intelligenceIndexCostPerTask"),
            "price_input_per_1M": g("price1mInputTokens"), "price_output_per_1M": g("price1mOutputTokens"),
            "price_cache_hit_per_1M": g("cacheHitPrice"), "price_cache_write_per_1M": g("cacheWritePrice"),
            "blended_price_3to1_per_1M": blended, "output_tokens_per_s": g("medianOutputTokensPerSecond"),
            "ttft_s": g("medianTimeToFirstTokenSeconds"), "end_to_end_response_s": g("medianEndToEndResponseTimeSeconds"),
            "context_window": g("contextWindowTokens"), "release_date": rel.get(slug, ""),
            "gpqa_diamond": g("gpqa"), "hle": g("hle"), "terminal_bench_hard": g("terminalbenchHard"),
            "terminal_bench_4_0": g("terminalBench40"), "tau2_bench": g("tau2"), "ifbench": g("ifbench"),
            "aa_lcr": g("lcr"),
        })
    return rows


def parse_llm_api(payload):
    """Best-effort mapping of the AA v2 models API; the page parser is the fallback when this yields too little."""
    items = payload.get("data", payload) if isinstance(payload, dict) else payload
    rows = []
    for o in items or []:
        ev, pr = o.get("evaluations") or {}, o.get("pricing") or {}
        name = o.get("name", "")
        pin, pout = pr.get("price_1m_input_tokens"), pr.get("price_1m_output_tokens")
        idx = ev.get("artificial_analysis_intelligence_index")
        rows.append({
            "model": name, "base_model": base_of(name), "effort_mode": effort_of(name), "slug": o.get("slug", ""),
            "creator": (o.get("model_creator") or {}).get("name", ""), "open_weights": "", "reasoning": "",
            "deprecated": "n", "intelligence_index": "" if idx is None else idx,
            "cost_per_task_usd": o.get("intelligence_index_cost_per_task", ""),
            "price_input_per_1M": "" if pin is None else pin, "price_output_per_1M": "" if pout is None else pout,
            "blended_price_3to1_per_1M": pr.get("price_1m_blended_3_to_1", ""),
            "output_tokens_per_s": o.get("median_output_tokens_per_second", ""),
            "ttft_s": o.get("median_time_to_first_token_seconds", ""), "release_date": o.get("release_date", ""),
        })
    return rows


def fmt_blocks(txt):
    blocks = []
    for o in iter_objs(txt, "formatted"):
        if not isinstance(o.get("values"), dict):
            continue
        if o["formatted"].get("rank") == 1 or not blocks:
            blocks.append([])
        blocks[-1].append(o)
    return blocks


def parse_arena(html, price_key, unit, kind="elo"):
    """Block 0 of an arena leaderboard (overall board) -> normalised media rows."""
    blocks = fmt_blocks(mi.rsc_text(html))
    if not blocks:
        return []
    rows = []
    for o in blocks[0]:
        v = o["values"]
        price = v.get(price_key)
        rows.append({
            "model": v.get("name", ""), "creator": (v.get("creator") or {}).get("name", ""),
            "score": v.get("elo", ""), "score_kind": kind, "price": "" if price is None else price,
            "price_unit": unit, "speed": "", "release_date": v.get("releaseDate", "") or "",
            "open_weights": "y" if (v.get("openWeightsUrl") or v.get("openWeights")) else "n",
            "rank": int(v.get("rank", len(rows))) + 1,
        })
    return rows


def parse_stt(html):
    merged = {}
    for key, arr in iter_arrays(mi.rsc_text(html)):
        if key == "data" and "Provider" in arr[0] and "Model" in arr[0]:
            for o in arr:
                merged.setdefault((o["Model"], o["Provider"]), {}).update(o)
    rows = []
    for (model, prov), o in merged.items():
        if o.get("AA-WER Index") is None:
            continue
        rows.append({"model": model, "creator": prov, "score": o.get("AA-WER Index"), "score_kind": "wer",
                     "price": o.get("Price per 1k Min", ""), "price_unit": "usd_per_1k_min",
                     "speed": o.get("Speed Factor", ""), "release_date": "", "open_weights": "", "rank": 0})
    rows.sort(key=lambda r: r["score"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


PARSERS = {
    "llm.html": lambda h: parse_llm(h),
    "text-to-image.html": lambda h: parse_arena(h, "pricePer1kImages", "usd_per_1k_images"),
    "image-editing.html": lambda h: parse_arena(h, "pricePer1kImages", "usd_per_1k_images"),
    "text-to-video.html": lambda h: parse_arena(h, "pricePerMinute", "usd_per_minute"),
    "image-to-video.html": lambda h: parse_arena(h, "pricePerMinute", "usd_per_minute"),
    "tts.html": lambda h: parse_arena(h, "pricePer1mCharacters", "usd_per_1m_chars"),
    "stt.html": parse_stt,
}


def http_get(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def llm_from_api(key):
    for path in ("/data/llms/models", "/language/models"):
        try:
            rows = parse_llm_api(json.loads(http_get(API + path, {"x-api-key": key})))
        except Exception as e:
            print(f"fetch: API {path} failed: {e}", file=sys.stderr)
            continue
        if rows and sum(1 for r in rows if r["cost_per_task_usd"] != "") >= len(rows) / 2:
            return rows
        print(f"fetch: API {path} lacks cost-per-task, using public page", file=sys.stderr)
    return None


def collect(from_dir):
    out = {}
    for fname, (path, csvname) in PAGES.items():
        if from_dir:
            p = os.path.join(from_dir, fname)
            if not os.path.exists(p):
                raise RuntimeError(f"missing {p}")
            html = Path(p).read_text(encoding="utf-8")
        else:
            if fname == "llm.html" and os.environ.get("AA_API_KEY"):
                rows = llm_from_api(os.environ["AA_API_KEY"])
                if rows:
                    out[csvname] = rows
                    continue
            html = http_get(BASE + path)
        out[csvname] = PARSERS[fname](html)
    return out


def check_drop(new, prev_dir):
    """Return list of problems: empty parse or >30% row-count drop vs the previous latest."""
    bad = []
    for name, rows in new.items():
        if not rows:
            bad.append(f"{name}: 0 rows parsed (page format changed?)")
            continue
        if prev_dir and (prev_dir / name).exists():
            old = len(mi.read_csv(prev_dir / name))
            if old and len(rows) < 0.7 * old:
                bad.append(f"{name}: rows {old} -> {len(rows)} (drop > 30%)")
    return bad


def main(argv):
    from_dir = argv[argv.index("--from-dir") + 1] if "--from-dir" in argv else None
    try:
        new = collect(from_dir)
    except Exception as e:
        print(f"fetch FAILED: {e}", file=sys.stderr)
        return 1
    prev = mi.latest_dir()
    bad = check_drop(new, prev)
    if bad:
        print("fetch FAILED, previous latest kept:\n  " + "\n  ".join(bad), file=sys.stderr)
        return 1
    snaps = mi.DATA / "snapshots"
    dest, tmp = snaps / mi.today(), snaps / (".tmp-" + mi.today())
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    for name, rows in new.items():
        mi.write_csv(tmp / name, rows, mi.LLM_COLS if name == "llm.csv" else mi.MEDIA_COLS)
    shutil.rmtree(dest, ignore_errors=True)
    tmp.rename(dest)
    link = mi.DATA / "latest"
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(dest)
    for name, rows in new.items():
        print(f"{name}: {len(rows)} rows")
    print(f"snapshot {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
