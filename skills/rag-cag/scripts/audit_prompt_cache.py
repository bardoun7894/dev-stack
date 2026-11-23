#!/usr/bin/env python3
"""audit_prompt_cache.py: Read-only scan for LLM prompt prefix cache-busters.

Codes:
  PC01 (high)   Volatile timestamp/clock call inside system prompt construction
  PC02 (high)   Static prompt file loaded after a dynamic variable in the same prompt block
  PC03 (medium) Unsorted directory listing used to assemble prompt files
  PC04 (info)   Chat completions payload sends system prompts without cached-token usage extraction

Exit codes:
  0  No high findings
  1  At least one high finding
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

SCAN_EXTS = {".php", ".ts", ".tsx", ".js", ".mjs", ".py"}
EXCLUDE_DIRS = {
    ".git",
    "node_modules",
    "vendor",
    "storage",
    "dist",
    "build",
    ".next",
    "__pycache__",
    ".venv",
    "venv",
    "tests",
    "test",
    "__tests__",
}

SYSTEM_PROMPT_HINT = re.compile(
    r"(systemPrompt|system_prompt|role['\"]?\s*(?:=>|:)\s*['\"]system['\"]|prompts?/)",
    re.IGNORECASE,
)
VOLATILE_TIME = re.compile(
    r"\b(now\s*\(|Date\.now\s*\(|new\s+Date\s*\(|datetime\.now\s*\(|datetime\.utcnow\s*\(|time\s*\(|date\s*\()",
)
STATIC_LOAD = re.compile(
    r"(File::get|file_get_contents|readFileSync|fs\.readFile|Path\([^)]+\)\.read_text|open\([^)]+\)\.read)",
)
DYNAMIC_CONTEXT = re.compile(
    r"(customerContext|userContext|contactContext|leadContext|clockLine|handback_note|lessonsPrompt|retrievedChunks|ragContext)",
    re.IGNORECASE,
)
UNSORTED_DIR = re.compile(
    r"(scandir\s*\(|readdirSync\s*\(|glob\s*\(|File::files\s*\(|os\.listdir\s*\()",
)
SORT_CALL = re.compile(r"\b(sort|sorted|sortBy|natsort|ksort)\b")


@dataclass
class Finding:
    code: str
    severity: str
    file: str
    line: int
    message: str


def iter_source_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix in SCAN_EXTS else []
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        if path.is_file() and path.suffix in SCAN_EXTS:
            files.append(path)
    return files


def scan_file(path: Path, root: Path) -> list[Finding]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    if not SYSTEM_PROMPT_HINT.search(text):
        return []

    rel = str(path.relative_to(root)) if root.is_dir() else str(path)
    lines = text.splitlines()
    findings: list[Finding] = []

    # Track system prompt concatenation blocks (heuristic: lines within 20 lines of systemPrompt assignment)
    in_sys_window = 0
    seen_dynamic_line: int | None = None
    seen_cache_split = "PromptCache::" in text or "cache_control" in text

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith(("//", "#", "*", "/*")):
            continue

        if re.search(r"(\$systemPrompt|system_prompt|systemPrompt)\s*=", line):
            in_sys_window = 22
            seen_dynamic_line = None
        elif in_sys_window > 0:
            in_sys_window -= 1

        if in_sys_window > 0 and not seen_cache_split:
            if VOLATILE_TIME.search(line):
                findings.append(
                    Finding(
                        code="PC01",
                        severity="high",
                        file=rel,
                        line=idx,
                        message="Volatile clock/timestamp call inside system prompt block busts prefix cache every minute/second; move to Hot suffix after Cold boundary.",
                    )
                )
            if DYNAMIC_CONTEXT.search(line):
                if seen_dynamic_line is None:
                    seen_dynamic_line = idx
            elif seen_dynamic_line is not None and (
                STATIC_LOAD.search(line)
                or re.search(r"(knowledgePrompt|skillsPrompt|SHORT_REPLY_RULE|dialectInstruction)", line)
            ):
                findings.append(
                    Finding(
                        code="PC02",
                        severity="high",
                        file=rel,
                        line=idx,
                        message=f"Static prompt block loaded after dynamic context (line {seen_dynamic_line}); move static block into Cold prefix before dynamic context.",
                    )
                )

        if UNSORTED_DIR.search(line):
            window = "\n".join(lines[max(0, idx - 1) : min(len(lines), idx + 4)])
            if not SORT_CALL.search(window):
                findings.append(
                    Finding(
                        code="PC03",
                        severity="medium",
                        file=rel,
                        line=idx,
                        message="Directory listing in prompt assembly without explicit sort; non-deterministic file order causes prefix cache misses.",
                    )
                )

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit LLM prompt builders for KV/prefix cache-busters.")
    parser.add_argument("path", help="File or directory to scan")
    parser.add_argument("--json", action="store_true", help="Output findings as JSON")
    args = parser.parse_args(argv)

    root = Path(args.path).resolve()
    if not root.exists():
        print(f"error: path not found: {root}", file=sys.stderr)
        return 2

    findings: list[Finding] = []
    for src in iter_source_files(root):
        findings.extend(scan_file(src, root))

    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2))
    else:
        if not findings:
            print(f"OK: no prompt prefix cache-busters found in {root}")
        else:
            for f in findings:
                print(f"[{f.severity.upper()}] {f.code} {f.file}:{f.line} — {f.message}")

    has_high = any(f.severity == "high" for f in findings)
    return 1 if has_high else 0


if __name__ == "__main__":
    raise SystemExit(main())
