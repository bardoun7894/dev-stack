#!/usr/bin/env python3
"""capability-outcomes — label skill-suggest decisions with what the session actually used (System 2 for Jev).

For each Choice decision under tag skill-suggest (the wide pick, and the rerank winner when the rerank was shown
to the agent) find the session turn it fired for (prompt text + timestamp window; ambiguous -> skipped), then look
at skills/agents used in that turn and the next N-1 turns (turns.jsonl + usage.jsonl from capability-scan.py):
  suggested X, X used          -> outcome X
  suggested X, Y used instead  -> outcome Y (first used)
  suggested X, nothing used    -> outcome none, only if the session clearly went on (>= 2 more turns)
Outcomes go through bin/jev's log_outcome; an id that already has an outcome is never written twice.

  capability-outcomes.py [--turns N] [--window S] [--dry-run]
Env: DEVSTACK_STATE, JEV_LOG_DIR.
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
TAG = "skill-suggest"
WIDE_PREFIX = "Which installed agent skill"
RERANK_PREFIX = "Which of these skills"
MIN_FOLLOWUP_TURNS = 2
GATE_PROMPTS = ("`request` asks the agent to act on the user", "Doing `request` well needs a specific", "A plain written answer alone")
GATE_KEYS = ("acts_on_user_system", "would_follow_documented_procedure", "prose_suffices")
REQUEST = re.compile(r'"request": "((?:[^"\\]|\\.)*)')


def load_jev():
    loader = importlib.machinery.SourceFileLoader("jev_outcomes", os.path.join(HERE, "..", "bin", "jev"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


_THRESHOLDS = None


def thresholds():
    """bin/jev-skill-suggest itself: its GATE_THRESHOLD / FITS_THRESHOLD / WIDE_BYPASS_CONFIDENCE / gate_score are the
    single source of truth for what the agent was shown, so nothing here keeps a copy."""
    global _THRESHOLDS
    if _THRESHOLDS is None:
        loader = importlib.machinery.SourceFileLoader("jev_skill_suggest_live", os.path.join(HERE, "..", "bin", "jev-skill-suggest"))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        _THRESHOLDS = importlib.util.module_from_spec(spec)
        loader.exec_module(_THRESHOLDS)
    return _THRESHOLDS


def state_dir():
    return os.environ.get("DEVSTACK_STATE") or os.path.expanduser("~/.local/state/dev-stack")


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def request_of(rec):
    m = REQUEST.search(rec.get("state_preview") or "")
    if not m:
        return ""
    raw = m.group(1).rstrip("\\")
    try:
        return norm(json.loads('"' + raw + '"'))
    except ValueError:
        return norm(raw.replace("\\n", " ").replace('\\"', '"'))


def prefix_match(a, b):
    n = min(len(a), len(b))
    return a[:n] == b[:n]


def read_jsonl(path):
    try:
        with open(path) as f:
            for line in f:
                try:
                    yield json.loads(line)
                except ValueError:
                    continue
    except OSError:
        return


def load_decisions(jev):
    decisions, noul, done = [], {}, set()
    try:
        f = open(jev.log_path())
    except OSError:
        return [], {}, set()
    with f:
        for line in f:
            is_out = '"kind_of_record": "outcome"' in line
            if not is_out and TAG not in line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("kind_of_record") == "outcome":
                done.add(r["id"])
            elif r.get("tag") == TAG and r.get("engine", "jev") == "jev":  # Laya fallback answers never train Jev
                instr = str((r.get("question") or {}).get("instructions", ""))
                if r.get("kind") == "choice" and (instr.startswith(WIDE_PREFIX) or instr.startswith(RERANK_PREFIX)):
                    decisions.append(r)
                elif r.get("kind") == "noul" and (instr.startswith("The skill `") or instr.startswith(GATE_PROMPTS)):
                    noul.setdefault(r.get("state_hash"), []).append(r)
    return decisions, noul, done


def shown(rec, noul):
    """Would the live gate have let this decision reach the agent? A rerank winner needs its OWN 'fits' score at
    FITS_THRESHOLD; a wide pick needs the gate mean at GATE_THRESHOLD or a confidence at WIDE_BYPASS_CONFIDENCE."""
    t = thresholds()
    near = [x for x in noul.get(rec.get("state_hash"), []) if abs(x["ts"] - rec["ts"]) <= 5]
    if str(rec["question"]["instructions"]).startswith(RERANK_PREFIX):
        return any(str(x["question"]["instructions"]).startswith(f"The skill `{rec.get('value')}`")
                   and (x.get("value") or 0) >= t.FITS_THRESHOLD for x in near)
    if (rec.get("confidence") or 0) >= t.WIDE_BYPASS_CONFIDENCE:
        return True
    answers = {}
    for key, prompt in zip(GATE_KEYS, GATE_PROMPTS):
        got = [x.get("value") for x in near if str(x["question"]["instructions"]).startswith(prompt)]
        if not got or got[0] is None:
            return False
        answers[key] = {"noul": got[0]}
    return t.gate_score(answers) >= t.GATE_THRESHOLD



def run(state=None, turns=6, window=120, dry_run=False):
    state = state or state_dir()
    jev = load_jev()
    decisions, noul, done = load_decisions(jev)
    by_head, by_session = {}, {}
    for t in read_jsonl(os.path.join(state, "turns.jsonl")):
        by_head.setdefault(norm(t["prompt"])[:100], []).append(t)
        by_session.setdefault(t["session"], []).append(t["seq"])
    used = {}
    for e in read_jsonl(os.path.join(state, "usage.jsonl")):
        if e.get("kind") in ("skill", "agent") and e.get("via") != "jdelegate" and not e.get("sub"):
            used.setdefault(e["session"], []).append(e)
    c = {k: 0 for k in ("followed", "other", "none", "already", "skipped_unmatched", "skipped_ambiguous",
                        "skipped_no_evidence", "skipped_not_shown", "skipped_bad_label", "written")}
    for rec in decisions:
        if rec["id"] in done:
            c["already"] += 1
            continue
        if not shown(rec, noul):
            c["skipped_not_shown"] += 1
            continue
        req = request_of(rec)
        cands = {(t["session"], t["seq"]): t for t in by_head.get(req[:100], [])
                 if req and abs(t["ts"] - rec["ts"]) <= window and prefix_match(norm(t["prompt"]), req)}
        if not cands:
            c["skipped_unmatched"] += 1
            continue
        if len(cands) > 1:
            c["skipped_ambiguous"] += 1
            continue
        (session, seq), = cands
        first = sorted((e for e in used.get(session, []) if seq <= e.get("seq", 0) < seq + turns),
                       key=lambda e: (e["ts"], e.get("seq", 0)))
        names = [("agent:" if e["kind"] == "agent" else "") + e["name"] for e in first]
        suggested = rec.get("value")
        if names:
            outcome = suggested if suggested in names else names[0]
            kind = "followed" if outcome == suggested else "other"
        elif sum(1 for s in by_session.get(session, []) if s > seq) >= MIN_FOLLOWUP_TURNS:
            outcome, kind = "none", "none"
        else:
            c["skipped_no_evidence"] += 1
            continue
        if outcome not in (rec["question"].get("criteria") or {}):  # only a label this decision could have chosen
            c["skipped_bad_label"] += 1
            continue
        c[kind] += 1
        if not dry_run:
            jev.log_outcome(rec["id"], outcome)
            c["written"] += 1
    return c


def main(argv):
    turns = int(argv[argv.index("--turns") + 1]) if "--turns" in argv else 6
    window = int(argv[argv.index("--window") + 1]) if "--window" in argv else 120
    c = run(turns=turns, window=window, dry_run="--dry-run" in argv)
    print("  ".join(f"{k}={v}" for k, v in c.items()))
    judged = c["followed"] + c["other"] + c["none"]
    if judged:
        print(f"precision (followed / judged) = {c['followed'] / judged:.2f} over {judged}")


if __name__ == "__main__":
    main(sys.argv[1:])
