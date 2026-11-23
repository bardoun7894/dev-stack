"""Regression tests for skills/rag-cag/scripts/audit_prompt_cache.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "audit_prompt_cache.py"


def run_audit(target: Path) -> tuple[int, list[dict]]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(target), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, json.loads(proc.stdout)


def test_detects_volatile_clock_and_static_after_dynamic(tmp_path: Path) -> None:
    bad = tmp_path / "BadPrompt.php"
    bad.write_text(
        """<?php
class BadPrompt {
    public function build($contact, $conversation) {
        $systemPrompt = File::get('prompts/base.md')
            . $this->customerContext($contact, $conversation)
            . $this->knowledgePrompt()
            . now()->format('Y-m-d H:i');
        return [['role' => 'system', 'content' => $systemPrompt]];
    }
}
""",
        encoding="utf-8",
    )
    code, findings = run_audit(bad)
    codes = {f["code"] for f in findings}
    assert code == 1
    assert "PC01" in codes
    assert "PC02" in codes


def test_passes_clean_cold_hot_split(tmp_path: Path) -> None:
    good = tmp_path / "GoodPrompt.php"
    good.write_text(
        """<?php
class GoodPrompt {
    public function build($contact, $conversation) {
        $cold = File::get('prompts/base.md') . $this->knowledgePrompt();
        $hot = $this->customerContext($contact, $conversation) . "\\nNow: " . now()->format('Y-m-d H:i');
        return [PromptCache::systemMessage($cold, $hot)];
    }
}
""",
        encoding="utf-8",
    )
    code, findings = run_audit(good)
    assert code == 0
    assert findings == []


def test_detects_unsorted_directory_scan(tmp_path: Path) -> None:
    unsorted = tmp_path / "skills.ts"
    unsorted.write_text(
        """
export function buildSystemPrompt(dir: string) {
  const files = fs.readdirSync(dir);
  return { role: 'system', content: files.join('\\n') };
}
""",
        encoding="utf-8",
    )
    code, findings = run_audit(unsorted)
    assert code == 0  # medium severity only
    assert [f["code"] for f in findings] == ["PC03"]
