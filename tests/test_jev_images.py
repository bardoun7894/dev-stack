"""jev --image / jev box: assets, header, refusals, metadata stripping, limits, routing, dry-run (no network)."""
import base64
import io
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from unittest import mock

from test_jev_log import BIN, load

jev = load("jev")
JEV = os.path.join(BIN, "jev")
FAKE_TS = "fake-" + "typesafe-" + "token0"


def png_chunk(ctype, data):
    return struct.pack(">I", len(data)) + ctype + data + struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)


def make_png(w=300, h=300, payload=b"\x00\x00\x00\x00", extra_chunks=b""):
    ihdr = png_chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    idat = png_chunk(b"IDAT", payload)
    iend = png_chunk(b"IEND", b"")
    return b"\x89PNG\r\n\x1a\n" + ihdr + extra_chunks + idat + iend


def make_jpg(w=300, h=300, extra_segs=b""):
    app0 = b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof0 = b"\xff\xc0\x00\x0b\x08" + struct.pack(">HH", h, w) + b"\x01\x01\x11\x00"
    sos = b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00\x00\xff\xd9"
    return b"\xff\xd8" + app0 + extra_segs + sof0 + sos


PNG = make_png()
JPG = make_jpg()


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
        os.environ.pop("JEV_DECISIONS_URL", None)
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
                mock.patch("sys.stdin", io.StringIO("")), mock.patch("sys.stderr", io.StringIO()):
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
        self.assertEqual(base64.b64decode(body["assets"][refs[1]]["data_base64"]), JPG)
        self.assertEqual(body["model"], "jev-latest")

    def test_model_flag_does_not_mutate_env(self):
        sent, _, _ = self.run_cli("noul", "x", "--image", self.png, "--model", "jev-1.13")
        self.assertEqual(json.loads(sent[0].data)["model"], "jev-1.13")
        self.assertNotIn("JEV_TYPESAFE_MODEL", os.environ)
        sent2, _, _ = self.run_cli("noul", "x", "-s", "hello")
        self.assertEqual(json.loads(sent2[0].data)["model"], "jev-latest")

    def test_image_refused_when_jev_decisions_url_set(self):
        with mock.patch.dict(os.environ, {"JEV_DECISIONS_URL": "https://other.example/decisions", "OPENROUTER_API_KEY": "or-key"}):
            sent, code, _ = self.run_cli("noul", "is it signed?", "--image", self.png)
        self.assertNotEqual(code, 0)
        self.assertEqual(sent, [])

    def test_box(self):
        ans = {"type": "box", "box": {"top": 0.1, "bottom": 0.5, "left": 0.2, "right": 0.9}, "confidence": 0.92}
        sent, code, out = self.run_cli("box", "the signature", "--image", self.png, answer=ans)
        body = json.loads(sent[0].data)
        self.assertEqual(body["model"], "jev-latest")
        self.assertEqual(body["questions"]["q"]["type"], "box")
        self.assertEqual(json.loads(out)["box"]["left"], 0.2)
        self.assertEqual(code, 0)

    def test_box_dry_run_default_model(self):
        r = subprocess.run([sys.executable, JEV, "box", "the stamp", "--image", self.png, "--dry-run"],
                           capture_output=True, text=True, env={**os.environ, "HOME": self.tmp.name})
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["url"], jev.TYPESAFE_URL)
        self.assertEqual(out["body"]["model"], "jev-latest")

    def test_box_refuses_old_model(self):
        sent, code, _ = self.run_cli("box", "x", "--image", self.png, "--model", "jev-1.13")
        self.assertEqual((sent, code), ([], 4))

    def test_min_low_confidence_exits_2(self):
        ans = {"type": "box", "box": {"top": 0.1, "bottom": 0.5, "left": 0.2, "right": 0.9}, "confidence": 0.5}
        _, code, _ = self.run_cli("box", "the signature", "--image", self.png, "--min", "0.8", answer=ans)
        self.assertEqual(code, 2)
        _, code2, _ = self.run_cli("choice", "q?", "a=x", "b=y", "-s", "hi", "--min", "0.8",
                                   answer={"type": "choice", "choice": "a", "confidence": 0.5})
        self.assertEqual(code2, 2)

    def test_min_null_box_exits_2(self):
        ans = {"type": "box", "box": None, "confidence": 0.99}
        _, code, _ = self.run_cli("box", "the signature", "--image", self.png, "--min", "0.8", answer=ans)
        self.assertEqual(code, 2)

    def test_wrong_type_refused(self):
        gif = self.write("a.gif", b"GIF89a" + b"\x00" * 20)
        sent, code, _ = self.run_cli("choice", "q?", "a=x", "b=y", "--image", gif)
        self.assertEqual((sent, code), ([], 4))

    def test_dimensions_enforced(self):
        for w, h in ((279, 300), (300, 279), (1569, 300), (300, 1569)):
            sent, code, _ = self.run_cli("noul", "x", "--image", self.write(f"{w}x{h}.png", make_png(w, h)))
            self.assertEqual((sent, code), ([], 4), f"PNG {w}x{h}")
            sent, code, _ = self.run_cli("noul", "x", "--image", self.write(f"{w}x{h}.jpg", make_jpg(w, h)))
            self.assertEqual((sent, code), ([], 4), f"JPG {w}x{h}")
        for w, h in ((280, 1568), (1568, 280)):
            _, code, _ = self.run_cli("noul", "x", "--image", self.write(f"{w}x{h}.png", make_png(w, h)))
            self.assertEqual(code, 0)
            _, code, _ = self.run_cli("noul", "x", "--image", self.write(f"{w}x{h}.jpg", make_jpg(w, h)))
            self.assertEqual(code, 0)

    def test_exif_and_metadata_stripped(self):
        exif_payload = b"Exif\x00\x00GPS_LAT=33.57"
        app1 = b"\xff\xe1" + struct.pack(">H", len(exif_payload) + 2) + exif_payload
        com = b"\xff\xfe\x00\x08secret"
        jpg_with_exif = self.write("exif.jpg", make_jpg(extra_segs=app1 + com))
        png_with_meta = self.write("meta.png", make_png(
            extra_chunks=png_chunk(b"eXIf", b"GPS_LON=-7.58") + png_chunk(b"tEXt", b"Author\x00secret")
        ))
        sent, code, _ = self.run_cli("noul", "x", "--image", jpg_with_exif, "--image", png_with_meta)
        self.assertEqual(code, 0)
        body = json.loads(sent[0].data)
        refs = [i["asset"] for i in body["state"]]
        sent_jpg = base64.b64decode(body["assets"][refs[0]]["data_base64"])
        sent_png = base64.b64decode(body["assets"][refs[1]]["data_base64"])
        self.assertEqual(sent_jpg, JPG)
        self.assertNotIn(b"GPS_LAT", sent_jpg)
        self.assertEqual(sent_png, PNG)
        self.assertNotIn(b"GPS_LON", sent_png)
        self.assertNotIn(b"Author", sent_png)

    def test_size_limit_16mib_boundary_and_aggregate(self):
        overhead = len(make_png(payload=b""))
        exact = self.write("exact.png", make_png(payload=b"\x00" * (jev.MAX_IMAGE_BYTES - overhead)))
        self.assertEqual(os.path.getsize(exact), jev.MAX_IMAGE_BYTES)
        _, code, _ = self.run_cli("noul", "x", "--image", exact)
        self.assertEqual(code, 0)

        too_big = self.write("big.png", make_png(payload=b"\x00" * (jev.MAX_IMAGE_BYTES - overhead + 1)))
        self.assertEqual(os.path.getsize(too_big), jev.MAX_IMAGE_BYTES + 1)
        sent, code, _ = self.run_cli("noul", "x", "--image", too_big)
        self.assertEqual((sent, code), ([], 4))

        half = self.write("half1.png", make_png(payload=b"\x00" * (jev.MAX_IMAGE_BYTES // 2 + 100)))
        half2 = self.write("half2.png", make_png(payload=b"\x00" * (jev.MAX_IMAGE_BYTES // 2 + 100)))
        sent, code, _ = self.run_cli("noul", "x", "--image", half, "--image", half2)
        self.assertEqual((sent, code), ([], 4))

    def test_jpeg_trailer_after_eoi_stripped(self):
        exif_payload = b"Exif\x00\x00GPS_TRAILER=1"
        app1 = b"\xff\xe1" + struct.pack(">H", len(exif_payload) + 2) + exif_payload
        trailer = b"\xff\xd8" + app1 + b"\xff\xd9"
        path = self.write("trailer.jpg", make_jpg() + trailer)
        sent, code, _ = self.run_cli("noul", "x", "--image", path)
        self.assertEqual(code, 0)
        body = json.loads(sent[0].data)
        ref = body["state"][0]["asset"]
        sent_jpg = base64.b64decode(body["assets"][ref]["data_base64"])
        self.assertNotIn(b"GPS_TRAILER", sent_jpg)

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
