#!/usr/bin/env python3
"""kitchen_sink.py: write one realistic admin screen (navbar, stats, table, form, alerts,
pills, pagination, modal) that uses the components a theme must get right, to compare a
theme before/after, light/dark, LTR/RTL.

    python3 kitchen_sink.py --css bootstrap.min.css [--css bs-theme.css] [--dir rtl]
        [--theme dark] [--inline] --out page.html

Screenshot (Chrome headless):
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new \
      --window-size=1360,1500 --hide-scrollbars --screenshot=out.png file:///abs/page.html
"""
from __future__ import annotations

import argparse
from pathlib import Path

T = {
    "en": dict(brand="Atlas Ops", nav=["Dashboard", "Orders", "Customers", "Reports"],
               search="Search orders", title="Orders", sub="All orders from the last 30 days",
               export="Export", new="New order", stats=[("Revenue", "184,320 MAD", "+12.4%"),
               ("Orders", "1,284", "+3.1%"), ("Avg. basket", "143 MAD", "-1.8%"),
               ("Returns", "2.1%", "-0.4%")], recent="Recent orders",
               cols=["Order", "Customer", "Date", "Status", "Total"],
               rows=[("#10482", "Karim El Idrissi", "18 Nov", "Paid", "1,240.00"),
                     ("#10481", "Salma Benali", "18 Nov", "Pending", "386.50"),
                     ("#10480", "Atlas Trans SARL", "17 Nov", "Shipped", "12,900.00"),
                     ("#10479", "Youssef Amrani", "17 Nov", "Refunded", "220.00"),
                     ("#10478", "Nadia Berrada", "16 Nov", "Paid", "2,015.75")],
               status={"Paid": "success", "Pending": "warning", "Shipped": "primary",
                       "Refunded": "secondary"},
               form="Quick order", customer="Customer", customer_ph="Name or phone",
               channel="Channel", channels=["Shop", "WhatsApp", "Phone"], amount="Amount",
               email="Email", email_bad="not-an-email", email_err="Enter a valid email address.",
               notify="Send WhatsApp confirmation", agree="Customer accepted the terms",
               help="We never share the number.", save="Save order", cancel="Cancel",
               info="3 orders are waiting for stock.", tabs=["All", "Paid", "Pending", "Refunded"],
               modal="Delete order #10479?", modal_body="This cannot be undone.", delete="Delete",
               progress="Monthly target"),
    "ar": dict(brand="أطلس", nav=["لوحة التحكم", "الطلبات", "الزبناء", "التقارير"],
               search="ابحث في الطلبات", title="الطلبات", sub="كل الطلبات في آخر 30 يوما",
               export="تصدير", new="طلب جديد", stats=[("المداخيل", "184٬320 درهم", "+12.4%"),
               ("الطلبات", "1٬284", "+3.1%"), ("متوسط السلة", "143 درهم", "-1.8%"),
               ("المرتجعات", "2.1%", "-0.4%")], recent="أحدث الطلبات",
               cols=["الطلب", "الزبون", "التاريخ", "الحالة", "المجموع"],
               rows=[("#10482", "كريم الإدريسي", "18 نونبر", "مدفوع", "1٬240٫00"),
                     ("#10481", "سلمى بنعلي", "18 نونبر", "قيد الانتظار", "386٫50"),
                     ("#10480", "أطلس ترانس", "17 نونبر", "تم الشحن", "12٬900٫00"),
                     ("#10479", "يوسف العمراني", "17 نونبر", "مسترجع", "220٫00"),
                     ("#10478", "نادية برادة", "16 نونبر", "مدفوع", "2٬015٫75")],
               status={"مدفوع": "success", "قيد الانتظار": "warning", "تم الشحن": "primary",
                       "مسترجع": "secondary"},
               form="طلب سريع", customer="الزبون", customer_ph="الاسم أو الهاتف",
               channel="القناة", channels=["المتجر", "واتساب", "الهاتف"], amount="المبلغ",
               email="البريد الإلكتروني", email_bad="بريد-غير-صحيح",
               email_err="أدخل بريدا إلكترونيا صحيحا.", notify="أرسل تأكيدا عبر واتساب",
               agree="وافق الزبون على الشروط", help="لن نشارك الرقم مع أحد.", save="حفظ الطلب",
               cancel="إلغاء", info="3 طلبات تنتظر توفر المخزون.",
               tabs=["الكل", "مدفوع", "قيد الانتظار", "مسترجع"], modal="حذف الطلب #10479؟",
               modal_body="لا يمكن التراجع عن هذا.", delete="حذف", progress="هدف الشهر"),
}


def page(css_tags: str, d: str, theme: str, s: dict) -> str:
    lang = "ar" if d == "rtl" else "en"
    nav = "".join(f'<li class="nav-item"><a class="nav-link{" active" if i == 1 else ""}" '
                  f'href="#">{n}</a></li>' for i, n in enumerate(s["nav"]))
    stats = "".join(
        f'<div class="col-6 col-lg-3"><div class="card h-100"><div class="card-body">'
        f'<div class="text-body-secondary small mb-1">{k}</div><div class="fs-4 fw-semibold">'
        f'{v}</div><div class="small {"text-success" if dv.startswith("+") else "text-danger"}'
        f'">{dv}</div></div></div></div>' for k, v, dv in s["stats"])
    rows = "".join(
        f'<tr><td class="fw-medium">{o}</td><td>{c}</td><td class="text-body-secondary">{dt}'
        f'</td><td><span class="badge text-bg-{s["status"][st]}">{st}</span></td>'
        f'<td class="text-end font-monospace">{t}</td></tr>' for o, c, dt, st, t in s["rows"])
    tabs = "".join(f'<li class="nav-item"><a class="nav-link{" active" if i == 0 else ""}" '
                   f'href="#">{t}</a></li>' for i, t in enumerate(s["tabs"]))
    opts = "".join(f"<option>{c}</option>" for c in s["channels"])
    ths = "".join(f'<th{" class=text-end" if i == 4 else ""}>{c}</th>'
                  for i, c in enumerate(s["cols"]))
    return f"""<!doctype html>
<html lang="{lang}" dir="{d}" data-bs-theme="{theme}">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kitchen sink</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=IBM+Plex+Sans+Arabic:wght@400;500;600&display=swap" rel="stylesheet">
{css_tags}
</head><body>
<nav class="navbar navbar-expand-lg bg-body border-bottom"><div class="container-fluid px-4">
<a class="navbar-brand fw-semibold" href="#">{s["brand"]}</a>
<ul class="navbar-nav me-auto">{nav}</ul>
<input class="form-control w-auto" type="search" placeholder="{s["search"]}">
<div class="dropdown ms-3"><button class="btn btn-outline-secondary btn-sm dropdown-toggle">MB</button></div>
</div></nav>
<main class="container-fluid px-4 py-4">
<div class="d-flex flex-wrap align-items-center gap-3 mb-4"><div class="me-auto">
<h1 class="h3 mb-1">{s["title"]}</h1><div class="text-body-secondary">{s["sub"]}</div></div>
<button class="btn btn-outline-secondary">{s["export"]}</button>
<button class="btn btn-primary">{s["new"]}</button></div>
<div class="row g-3 mb-4">{stats}</div>
<div class="alert alert-info d-flex align-items-center gap-2">{s["info"]}</div>
<div class="row g-4"><div class="col-lg-8">
<div class="card"><div class="card-header d-flex align-items-center bg-transparent">
<span class="me-auto">{s["recent"]}</span><ul class="nav nav-pills nav-sm">{tabs}</ul></div>
<div class="table-responsive"><table class="table table-hover align-middle mb-0">
<thead><tr>{ths}</tr></thead><tbody>{rows}</tbody></table></div>
<div class="card-footer bg-transparent d-flex align-items-center">
<div class="flex-grow-1 me-4"><div class="small text-body-secondary mb-1">{s["progress"]}</div>
<div class="progress" style="height:.5rem"><div class="progress-bar" style="width:68%"></div></div></div>
<ul class="pagination pagination-sm mb-0"><li class="page-item"><a class="page-link" href="#">1</a></li>
<li class="page-item active"><a class="page-link" href="#">2</a></li><li class="page-item"><a class="page-link" href="#">3</a></li></ul>
</div></div></div>
<div class="col-lg-4"><div class="card"><div class="card-header bg-transparent">{s["form"]}</div><div class="card-body">
<div class="mb-3"><label class="form-label" for="c">{s["customer"]}</label>
<input class="form-control" id="c" placeholder="{s["customer_ph"]}" aria-describedby="ch">
<div class="form-text" id="ch">{s["help"]}</div></div>
<div class="row g-3 mb-3"><div class="col-6"><label class="form-label" for="ch2">{s["channel"]}</label>
<select class="form-select" id="ch2">{opts}</select></div>
<div class="col-6"><label class="form-label" for="a">{s["amount"]}</label>
<div class="input-group"><input class="form-control" id="a" value="1240"><span class="input-group-text">MAD</span></div></div></div>
<div class="mb-3"><label class="form-label" for="e">{s["email"]}</label>
<input class="form-control is-invalid" id="e" value="{s["email_bad"]}"><div class="invalid-feedback">{s["email_err"]}</div></div>
<div class="form-check form-switch mb-2"><input class="form-check-input" type="checkbox" id="n" checked><label class="form-check-label" for="n">{s["notify"]}</label></div>
<div class="form-check mb-4"><input class="form-check-input" type="checkbox" id="t"><label class="form-check-label" for="t">{s["agree"]}</label></div>
<div class="d-flex gap-2"><button class="btn btn-primary flex-grow-1">{s["save"]}</button><button class="btn btn-outline-secondary">{s["cancel"]}</button></div>
</div></div>
<div class="modal position-static d-block mt-4" tabindex="-1"><div class="modal-dialog m-0"><div class="modal-content">
<div class="modal-header"><h2 class="modal-title h6">{s["modal"]}</h2><button type="button" class="btn-close" aria-label="Close"></button></div>
<div class="modal-body text-body-secondary">{s["modal_body"]}</div>
<div class="modal-footer"><button class="btn btn-outline-secondary">{s["cancel"]}</button><button class="btn btn-danger">{s["delete"]}</button></div>
</div></div></div></div></div>
</main></body></html>"""


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--css", action="append", required=True, help="stylesheet path or URL, in order")
    p.add_argument("--dir", default="ltr", choices=["ltr", "rtl"])
    p.add_argument("--theme", default="light", choices=["light", "dark"])
    p.add_argument("--inline", action="store_true", help="inline local CSS files")
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    tags = []
    for c in a.css:
        if a.inline and Path(c).is_file():
            tags.append(f"<style>{Path(c).read_text()}</style>")
        else:
            href = c if "://" in c else Path(c).resolve().as_uri()
            tags.append(f'<link rel="stylesheet" href="{href}">')
    s = T["ar" if a.dir == "rtl" else "en"]
    Path(a.out).write_text(page("\n".join(tags), a.dir, a.theme, s), encoding="utf-8")
    print(a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
