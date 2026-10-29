"""jev --image / jev box: assets, header, refusals, dry-run redaction (mocked HTTP, no network)."""
import base64
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from test_jev_log import BIN, load

jev = load("jev")
JEV = os.path.join(BIN, "jev")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
FAKE_TS = "fake-" + "typesafe-" + "token0"
JPG = b"\xff\xd8\xff\xe0" + b"\x01" * 64


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class ImagesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": FAKE_TS, "JEV_NO_LAYA": "1"})
        self.env.start()
        os.environ.pop("JEV_DRY_RUN", None)
        os.environ.pop("JEV_TYPESAFE_MODEL", None)
        self.png = self.write("a.png", PNG)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def write(self, name, data):
        p = os.path.join(self.tmp.name, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    def run_cli(self, *args, answer=None):
        """Run main() with urlopen mocked. Returns (requests, exit code, stdout)."""
        sent = []

        def fake(req, timeout=None):
            sent.append(req)
            return FakeResp(json.dumps({"answers": {"q": answer or {"type": "choice", "choice": "a", "confidence": 0.9}}}).encode())

        out = io.StringIO()
        code = 0
        with mock.patch("urllib.request.urlopen", fake), mock.patch("sys.stdout", out), \
                mock.patch("sys.stdin", io.StringIO("")):
            try:
                jev.main(list(args))
            except SystemExit as e:
                code = e.code
        return sent, code, out.getvalue()

    def test_header_only_with_image(self):
        sent, _, _ = self.run_cli("choice", "q?", "a=x", "b=y", "--image", self.png)
        self.assertEqual(sent[0].get_header("Typesafe-danger-zone-images"), "true")
        sent, _, _ = self.run_cli("choice", "q?", "a=x", "b=y", "-s", "hello")
        self.assertIsNone(sent[0].get_header("Typesafe-danger-zone-images"))
        self.assertNotIn("assets", json.loads(sent[0].data))

    def test_asset_uuid_referenced_and_default_model(self):
        sent, _, _ = self.run_cli("noul", "is it signed?", "--image", self.png, "--image", self.write("b.jpg", JPG))
        body = json.loads(sent[0].data)
        self.assertEqual(len(body["assets"]), 2)
        refs = [i["asset"] for i in body["state"]]
        self.assertEqual(sorted(refs), sorted(body["assets"]))
        a = body["assets"][refs[0]]
        self.assertEqual((a["type"], a["format"]), ("image", "png"))
        self.assertEqual(base64.b64decode(a["data_base64"]), PNG)
        self.assertEqual(body["assets"][refs[1]]["format"], "jpg")
        self.assertEqual(body["model"], "jev-latest")

    def test_model_flag(self):
        sent, _, _ = self.run_cli("noul", "x", "--image", self.png, "--model", "jev-1.13")
        self.assertEqual(json.loads(sent[0].data)["model"], "jev-1.13")

    def test_box(self):
        ans = {"type": "box", "box": {"top": 0.1, "bottom": 0.5, "left": 0.2, "right": 0.9}, "confidence": 0.92}
        sent, code, out = self.run_cli("box", "the signature", "--image", self.png, answer=ans)
        self.assertEqual(json.loads(sent[0].data)["questions"]["q"]["type"], "box")
        self.assertEqual(json.loads(out)["box"]["left"], 0.2)
        self.assertEqual(code, 0)

    def test_box_refuses_old_model(self):
        sent, code, _ = self.run_cli("box", "x", "--image", self.png, "--model", "jev-1.13")
        self.assertEqual((sent, code), ([], 2))

    def test_wrong_type_refused(self):
        gif = self.write("a.gif", b"GIF89a" + b"\x00" * 20)
        sent, code, _ = self.run_cli("choice", "q?", "a=x", "b=y", "--image", gif)
        self.assertEqual((sent, code), ([], 2))

    def test_too_big_refused(self):
        big = self.write("big.png", PNG + b"\x00" * jev.MAX_IMAGE_BYTES)
        sent, code, _ = self.run_cli("noul", "x", "--image", big)
        self.assertEqual((sent, code), ([], 2))

    def test_text_state_still_redacted(self):
        fake = "sk-or-v1-" + "a1B2c3D4e5F6" * 5
        sent, _, _ = self.run_cli("noul", "x", "-s", f"OPENROUTER_API_KEY={fake}", "--image", self.png)
        self.assertNotIn(fake, sent[0].data.decode())

    def test_dry_run_redacts_base64(self):
        r = subprocess.run([sys.executable, JEV, "noul", "x", "--image", self.png, "--dry-run"],
                           capture_output=True, text=True, env={**os.environ, "HOME": self.tmp.name})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"<image {len(PNG)} bytes>", r.stdout)
        self.assertNotIn(base64.b64encode(PNG).decode(), r.stdout)
        self.assertNotIn(FAKE_TS, r.stdout)


if __name__ == "__main__":
    unittest.main()
