"""notify.sh keeps the Telegram bot token out of curl's argv (stubbed curl, no network)."""
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

NOTIFY = Path(__file__).resolve().parent.parent / "scripts" / "notify.sh"
STUB = """#!/usr/bin/env bash
echo "ARGV: $*" >> "$OUT"
while [ $# -gt 0 ]; do [ "$1" = -K ] && echo "CONFIG: $(cat "$2")" >> "$OUT"; shift; done
cat > /dev/null
"""


class Notify(unittest.TestCase):
    def test_token_goes_through_a_config_pipe_not_argv(self):
        d = Path(tempfile.mkdtemp(prefix="mi-notify-"))
        (d / "curl").write_text(STUB)
        (d / "curl").chmod(stat.S_IRWXU)
        fake = "FAKE" + "123:abc"
        (d / "env").write_text(f"TELEGRAM_BOT_TOKEN={fake}\nTELEGRAM_USER_ID=42\n")
        env = dict(os.environ, OUT=str(d / "out"), PATH=f"{d}:{os.environ['PATH']}",
                   MODEL_INTEL_ENV_FILE=str(d / "env"), MODEL_INTEL_SSH_HOST="")
        subprocess.run(["bash", str(NOTIFY)], input="hello", text=True, env=env, check=True, timeout=30)
        out = (d / "out").read_text()
        argv = [ln for ln in out.splitlines() if ln.startswith("ARGV:")]
        self.assertEqual(len(argv), 1)
        self.assertNotIn(fake, argv[0])
        self.assertIn(f"bot{fake}/sendMessage", out)


if __name__ == "__main__":
    unittest.main()
