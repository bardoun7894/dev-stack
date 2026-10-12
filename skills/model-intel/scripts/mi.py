"""Shared helpers for model-intel (stdlib only)."""
import csv, datetime, json, os, re
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("MODEL_INTEL_DATA", SKILL / "data"))
TIERS = Path(os.environ.get("MODEL_INTEL_TIERS", Path.home() / ".config/jev-router/tiers.json"))
REAL_TIERS = Path.home() / ".config/jev-router/tiers.json"


def today():
    return os.environ.get("MODEL_INTEL_DATE") or datetime.date.today().isoformat()


def rsc_text(html):
    """Concatenate and decode the Next.js self.__next_f.push chunks of a page."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"((?:\\.|[^"\\])*)"\]\)', html)
    return "".join(json.loads('"' + c + '"') for c in chunks)


def snapshots(data=None):
    d = (data or DATA) / "snapshots"
    return sorted(p for p in d.iterdir() if p.is_dir()) if d.is_dir() else []


def latest_dir(data=None):
    link = (data or DATA) / "latest"
    return link.resolve() if link.exists() else None


def previous_dir(data=None):
    cur = latest_dir(data)
    prev = [p for p in snapshots(data) if cur is None or p.name < cur.name]
    return prev[-1] if prev else None


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, cols):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


EFFORT_RE = re.compile(r"-(max|xhigh|high|medium|low|minimal|non-reasoning|reasoning)$")


def family_key(slug):
    """AA slug without the effort suffix, normalised: claude-opus-5-5-xhigh -> claudeopus55."""
    return norm(EFFORT_RE.sub("", slug))


EFFORT_ORDER = ["non-reasoning", "minimal", "low", "medium", "high", "xhigh", "max", "default"]
LLM_COLS = ["model", "base_model", "effort_mode", "slug", "creator", "open_weights", "reasoning", "deprecated",
            "intelligence_index", "intelligence_index_estimated", "cost_per_task_usd", "price_input_per_1M",
            "price_output_per_1M", "price_cache_hit_per_1M", "price_cache_write_per_1M", "blended_price_3to1_per_1M",
            "output_tokens_per_s", "ttft_s", "end_to_end_response_s", "context_window", "release_date",
            "gpqa_diamond", "hle", "terminal_bench_hard", "terminal_bench_4_0", "tau2_bench", "ifbench", "aa_lcr"]
MEDIA_COLS = ["model", "creator", "score", "score_kind", "price", "price_unit", "speed", "release_date",
              "open_weights", "rank"]
MEDIA_FILES = ["media_text_to_image.csv", "media_image_editing.csv", "media_text_to_video.csv",
               "media_image_to_video.csv", "media_tts.csv", "media_stt.csv"]
