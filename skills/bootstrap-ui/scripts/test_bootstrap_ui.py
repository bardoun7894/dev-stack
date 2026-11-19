"""Offline tests on fixture projects. Run: python3 -m unittest test_bootstrap_ui -v"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import bs_doctor  # noqa: E402
import contrast  # noqa: E402

CDN5 = "https://cdn.jsdelivr.net/npm/bootstrap@5.3.9/dist"
CDN4 = "https://stackpath.bootstrapcdn.com/bootstrap/4.6.2"


def project(files: dict) -> str:
    d = tempfile.mkdtemp(prefix="bsdoc-")
    for rel, body in files.items():
        p = Path(d) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    return d


def codes(root, **kw):
    return {f["code"]: f for f in bs_doctor.run(root, **kw)["findings"]}


V = "resources/views/"


class DoctorTests(unittest.TestCase):
    def test_bs5_markup_on_bs4_layout(self):
        root = project({
            V + "layouts/app.blade.php": f'<link href="{CDN4}/css/bootstrap.min.css">@yield("c")',
            V + "orders.blade.php": "@extends('layouts.app')\n<div class=\"ms-3\">"
                                    "<a data-bs-toggle=\"modal\">x</a></div>",
        })
        c = codes(root)
        self.assertIn("bs5-on-bs4", c)
        self.assertNotIn("bs4-class", c)

    def test_bs4_classes_and_data_toggle_on_bs5(self):
        root = project({
            V + "layouts/app.blade.php": f'<link href="{CDN5}/css/bootstrap.min.css">',
            V + "a.blade.php": "@extends('layouts.app')\n<div class=\"form-group ml-2\">\n"
                               "<button data-toggle=\"modal\" data-target=\"#m\">x</button>\n"
                               "<i data-toggle=\"tooltip\" title=t></i>\n"
                               "<script>$('[data-toggle=tooltip]').tooltip()</script>",
        })
        c = codes(root)
        self.assertEqual(c["data-toggle"]["severity"], "high")
        self.assertIn("a.blade.php:3", c["data-toggle"]["samples"][0])
        self.assertNotIn("data-toggle-js", c)  # tooltip initialised by JS: not reported
        self.assertTrue(any(k == "bs4-class" for k in c))

    def test_if_alternative_heads_are_not_double_loads(self):
        root = project({
            V + "partials/head.blade.php": f'<link href="{CDN5}/css/bootstrap.min.css">',
            V + "partials/head_ar.blade.php": f'<link href="{CDN5}/css/bootstrap.rtl.min.css">',
            V + "layouts/app.blade.php": "<html dir=\"{{ $dir }}\">@if($rtl)\n"
                                         "@include('partials.head_ar')\n@else\n"
                                         "@include('partials.head')\n@endif",
            V + "x.blade.php": "@extends('layouts.app')",
        })
        c = codes(root)
        for k in ("double-css", "rtl-and-ltr", "rtl-css"):
            self.assertNotIn(k, c)

    def test_blade_asset_ref_with_local_header_and_js_mismatch(self):
        root = project({
            "public/theme/css/bootstrap.min.css": "/*!\n * Bootstrap v4.2.1 (x)\n */.ml-1{}",
            V + "layouts/admin.blade.php":
                "<link rel=stylesheet href=\"{{ asset('theme/css/bootstrap.min.css') }}\">\n"
                f"<script src=\"{CDN5}/js/bootstrap.bundle.min.js\"></script>",
            V + "p.blade.php": "@extends('layouts.admin')",
        })
        rep = bs_doctor.run(root)
        c = {f["code"]: f for f in rep["findings"]}
        self.assertIn("js-css-mismatch", c)
        self.assertIn("bs-css:4.2.1", " ".join(rep["layouts"][V + "layouts/admin.blade.php"]))

    def test_rtl_page_with_ltr_css(self):
        root = project({"public/a.html": f'<html lang="ar" dir="rtl"><link href="{CDN5}/css/'
                                          'bootstrap.min.css">'})
        self.assertIn("rtl-css", codes(root))

    def test_tailwind_preflight_read_from_compiled_css(self):
        on = project({
            "public/css/tw.css": "/*! tailwindcss v3.4.17 | MIT License */"
                                 "*,:after,:before{box-sizing:border-box;border:0 solid #e5e7eb}",
            "tailwind.config.js": "module.exports={prefix:'tw-'}",
            "public/a.html": f'<link href="{CDN5}/css/bootstrap.min.css"><link href="/css/tw.css">',
        })
        c = codes(on)
        self.assertIn("tw-preflight", c)
        self.assertNotIn("tw-clash", c)  # prefixed
        off = project({
            "public/css/tw.css": "/*! tailwindcss v3.4.17 | MIT License */.tw-flex{display:flex}",
            "tailwind.config.js": "module.exports={prefix:'tw-'}",
            "public/a.html": f'<link href="{CDN5}/css/bootstrap.min.css"><link href="/css/tw.css">',
        })
        self.assertNotIn("tw-preflight", codes(off))

    def test_monorepo_views_root_and_excludes(self):
        root = project({
            "pos/" + V + "layouts/app.blade.php": f'<link href="{CDN4}/css/bootstrap.min.css">',
            "pos/" + V + "p.blade.php": "@extends('layouts.app')\n<i class=\"ms-2\"></i>",
            "node_modules/x/index.html": "<div class=\"ml-3\" data-toggle=\"modal\"></div>",
        })
        rep = bs_doctor.run(root)
        self.assertIn("pos/" + V + "layouts/app.blade.php", rep["layouts"])
        self.assertIn("bs5-on-bs4", {f["code"] for f in rep["findings"]})
        self.assertFalse(any("node_modules" in s for f in rep["findings"] for s in f["samples"]))

    def test_mixed_versions_and_unpinned(self):
        root = project({
            "public/a.html": '<link href="https://cdn.jsdelivr.net/npm/bootstrap@5/dist/css/'
                             'bootstrap.min.css">',
            "public/b.html": f'<link href="{CDN4}/css/bootstrap.min.css">',
        })
        c = codes(root)
        self.assertIn("mixed-versions", c)
        self.assertIn("unpinned", c)

    def test_cli_exit_codes(self):
        clean = project({"public/a.html": f'<link href="{CDN5}/css/bootstrap.min.css" '
                                           'integrity="sha384-x" crossorigin="anonymous">'})
        r = subprocess.run([sys.executable, str(HERE / "bs_doctor.py"), clean],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(bs_doctor.main(["/nonexistent/dir"]), 2)


class ReviewRegressionTests(unittest.TestCase):
    def test_bs3_col_xs_12(self):
        root = project({"public/a.html": f'<link href="{CDN5}/css/bootstrap.min.css">'
                                          '<div class="col-xs-12"></div>'})
        self.assertIn("bs3-class", codes(root))

    def test_same_major_js_on_page_and_layout(self):
        root = project({
            V + "layouts/app.blade.php": f'<script src="{CDN5}/js/bootstrap.bundle.min.js">',
            V + "p.blade.php": "@extends('layouts.app')\n"
                               f'<script src="{CDN5}/js/bootstrap.min.js"></script>',
        })
        self.assertIn("double-js", codes(root))

    def test_score_css_is_not_a_theme(self):
        root = project({"public/a.html": f'<link href="{CDN5}/css/bootstrap.min.css" '
                                          'integrity="x"><link href="/css/score.css">',
                        "public/css/score.css": ".x{}"})
        self.assertNotIn("double-css", codes(root))

    def test_tailwind_v4_css_prefix_counts(self):
        root = project({
            "resources/css/app.css": '@import "tailwindcss" prefix(tw);',
            "public/css/tw.css": "/*! tailwindcss v4.1.11 | MIT License */.tw\\:flex{}",
            "public/a.html": f'<link href="{CDN5}/css/bootstrap.min.css"><link href="/css/tw.css">'
                             '<div class="collapse"></div>',
        })
        self.assertNotIn("tw-clash", codes(root))

    def test_sri_read_per_tag_and_from_layout(self):
        root = project({
            V + "layouts/app.blade.php": f'<link href="{CDN5}/css/bootstrap.min.css" '
                                         'integrity="sha384-x" crossorigin="anonymous">',
            V + "p.blade.php": "@extends('layouts.app')",
        })
        self.assertNotIn("no-sri", codes(root))

    def test_unparsed_color_fails(self):
        css = ":root{--bs-body-bg:hsl(0 0% 100%);--bs-body-color:#aaa}"
        rows = contrast.check(contrast.parse(css))
        self.assertTrue(rows and not all(r["ok"] for r in rows))

    def test_borderline_not_rounded_up(self):
        self.assertLess(contrast.ratio(contrast.color("#777777", {}),
                                       contrast.color("#ffffff", {})), 4.5)


class ContrastTests(unittest.TestCase):
    def test_ratio_math(self):
        self.assertEqual(contrast.ratio((0, 0, 0, 1), (1, 1, 1, 1)), 21.0)
        c = contrast.color("color-mix(in srgb, #000 50%, #fff)", {})
        self.assertAlmostEqual(c[0], 0.5, places=2)

    def test_failing_theme_detected(self):
        css = ":root{--bs-body-bg:#fff;--bs-body-color:#aaa;--bs-tertiary-bg:#fff}"
        rows = contrast.check(contrast.parse(css))
        self.assertFalse(all(r["ok"] for r in rows))

    def test_templates_pass(self):
        rows = contrast.check(contrast.parse(
            (HERE.parent / "templates" / "bs-theme.css").read_text()))
        bad = [r for r in rows if not r["ok"]]
        self.assertEqual(bad, [])


class DocTests(unittest.TestCase):
    def test_migration_doc_in_sync(self):
        r = subprocess.run([sys.executable, str(HERE / "gen_migration.py"), "--check"])
        self.assertEqual(r.returncode, 0, "run gen_migration.py")


if __name__ == "__main__":
    unittest.main()
