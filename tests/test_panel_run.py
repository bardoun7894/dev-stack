#!/usr/bin/env python3
"""Tests for bin/panel-run deterministic multi-reviewer runner."""

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BIN = REPO_ROOT / "bin" / "panel-run"


def _make_exec(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class PanelRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.out_dir = self.tmp_path / "panel-out"

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *args, env_extra=None):
        env = os.environ.copy()
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            ["python3", str(BIN), *args],
            capture_output=True,
            text=True,
            env=env,
            timeout=20,
        )

    def test_four_reviewer_parallel_rounds_and_compact_digest(self):
        codex_bin = _make_exec(
            self.tmp_path / "fake-codex",
            """#!/usr/bin/env python3
import sys
prompt = sys.argv[-1]
if "You are Reviewer B" in prompt:
    assert "PLAN A (Claude):" in prompt
    assert "PLAN C (Gemini):" in prompt
    assert "PLAN D (OpenCode/MiniMax):" in prompt
    print("`A:migration-lock` — confidence 5 — missing lock timeout — set lock_timeout=5s")
    print("`C:ui-step` — confidence 3 — minor ordering — swap step 2 and 3")
else:
    print("Codex R1 plan: use transactional DDL with lock_timeout.")
""",
        )
        gemini_bin = _make_exec(
            self.tmp_path / "fake-gemini",
            """#!/usr/bin/env python3
import sys
prompt = sys.argv[sys.argv.index("-p") + 1]
if "You are Reviewer C" in prompt:
    assert "PLAN B (Codex):" in prompt
    print("`A:migration-lock` — confidence 4 — agree lock timeout is mandatory — add retry")
else:
    print("Gemini R1 plan: stage tenant backfill in batches.")
""",
        )
        opencode_bin = _make_exec(
            self.tmp_path / "fake-opencode",
            """#!/usr/bin/env python3
import sys
prompt = sys.argv[2]
if "You are Reviewer D" in prompt:
    print("`B:rollout-copy` — confidence 4 — maintenance banner copy missing — add status banner")
else:
    print("OpenCode R1 plan: clarify tenant cutover UX state.")
""",
        )

        draft_a = self.tmp_path / "draft-a.md"
        draft_a.write_text("Claude R1 plan: add tenant_id column and backfill.\n", encoding="utf-8")
        prior_art = self.tmp_path / "prior.md"
        prior_art.write_text("- [[tenant-architecture]]: shared schema with RLS\n", encoding="utf-8")

        res = self._run(
            "--target",
            "multi-tenant migration",
            "--scope",
            "plan",
            "--slug",
            "tenant-mig",
            "--date",
            "2026-11-16",
            "--prior-art-file",
            str(prior_art),
            "--draft-a-file",
            str(draft_a),
            "--out-dir",
            str(self.out_dir),
            env_extra={
                "PANEL_CODEX_BIN": str(codex_bin),
                "PANEL_GEMINI_BIN": str(gemini_bin),
                "PANEL_OPENCODE_BIN": str(opencode_bin),
            },
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        # Compact stdout: must NOT dump full R1 bodies, must include paths and parsed scores
        self.assertNotIn("Codex R1 plan: use transactional DDL", res.stdout)
        self.assertIn("PANEL_MODE: 4-reviewer", res.stdout)
        self.assertIn("A:migration-lock", res.stdout)

        transcript = self.out_dir / "2026-11-16-tenant-mig.md"
        self.assertTrue(transcript.is_file())
        body = transcript.read_text(encoding="utf-8")
        self.assertIn("### Plan A (Claude)", body)
        self.assertIn("Codex R1 plan: use transactional DDL", body)
        self.assertIn("Gemini R1 plan: stage tenant backfill", body)
        self.assertIn("OpenCode R1 plan: clarify tenant cutover", body)
        self.assertIn("### Codex on A + C + D", body)

        digest = json.loads((self.out_dir / "2026-11-16-tenant-mig" / "digest.json").read_text(encoding="utf-8"))
        self.assertEqual(digest["panel_mode"], "4-reviewer")
        self.assertEqual(digest["active_external"], ["B", "C", "D"])
        self.assertGreaterEqual(len(digest["critiques"]), 3)

    def test_retries_transient_failure_once_and_falls_back_when_cli_missing(self):
        state_file = self.tmp_path / "codex-attempts"
        codex_flaky = _make_exec(
            self.tmp_path / "flaky-codex",
            f"""#!/usr/bin/env python3
from pathlib import Path
import sys
p = Path("{state_file}")
n = int(p.read_text()) + 1 if p.exists() else 1
p.write_text(str(n))
if n == 1:
    sys.stderr.write("transient network timeout\\n")
    sys.exit(1)
print("`A:edge-case` — confidence 5 — null check — guard None" if "Reviewer B" in sys.argv[-1] else "Codex R1 after retry")
""",
        )
        gemini_bin = _make_exec(
            self.tmp_path / "ok-gemini",
            """#!/usr/bin/env python3
import sys
p = sys.argv[sys.argv.index("-p") + 1]
print("`B:ok` — confidence 3 — solid — keep" if "Reviewer C" in p else "Gemini R1 ok")
""",
        )

        res = self._run(
            "--target",
            "auth check",
            "--scope",
            "review",
            "--slug",
            "auth-check",
            "--date",
            "2026-11-16",
            "--out-dir",
            str(self.out_dir),
            env_extra={
                "PANEL_CODEX_BIN": str(codex_flaky),
                "PANEL_GEMINI_BIN": str(gemini_bin),
                "PANEL_OPENCODE_BIN": str(self.tmp_path / "missing-opencode"),
            },
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("PANEL_MODE: 3-reviewer", res.stdout)
        self.assertIn("MISSING: D(opencode)", res.stdout)
        transcript = (self.out_dir / "2026-11-16-auth-check.md").read_text(encoding="utf-8")
        self.assertIn("Codex R1 after retry", transcript)

    def test_aborts_with_rc_2_when_all_external_clis_unavailable(self):
        res = self._run(
            "--target",
            "x",
            "--scope",
            "plan",
            "--slug",
            "none",
            "--out-dir",
            str(self.out_dir),
            env_extra={
                "PANEL_CODEX_BIN": str(self.tmp_path / "no-codex"),
                "PANEL_GEMINI_BIN": str(self.tmp_path / "no-gemini"),
                "PANEL_OPENCODE_BIN": str(self.tmp_path / "no-opencode"),
            },
        )
        self.assertEqual(res.returncode, 2)
        self.assertIn("All external reviewer CLIs unavailable", res.stderr)


if __name__ == "__main__":
    unittest.main()
