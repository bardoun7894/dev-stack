#!/usr/bin/env python3
"""
ai_debate.py: Multi-Model Debate Pipeline (Gemini -> Grok -> Claude).
Implements the Multi-Agent Debate technique (MIT / Google research) where
models critique each other's assumptions to arrive at a verified, robust synthesis.

Runs locally or over SSH on MyContabo server.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def run_cmd(cmd, timeout=180.0, stdin_data=None):
    """Run a shell command safely and return stdout."""
    res = subprocess.run(
        cmd,
        input=stdin_data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False
    )
    if res.returncode != 0:
        err = res.stderr.strip() or res.stdout.strip()
        print(f"Warning: command failed (code {res.returncode}): {err}", file=sys.stderr)
    return res.stdout.strip()


def call_gemini(prompt: str) -> str:
    """Invoke Gemini CLI (agy) as the Architect."""
    cmd = ["agy", "-p", prompt]
    return run_cmd(cmd, timeout=180.0)


def call_grok(prompt: str) -> str:
    """Invoke Grok CLI as the Devil's Advocate."""
    with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as tf:
        tf.write(prompt)
        tf_path = tf.name

    try:
        cmd = [
            "grok",
            "--model", "grok-4.7-build-fast",
            "--effort", "low",
            "--prompt-file", tf_path,
            "--output-format", "plain",
            "--always-approve"
        ]
        return run_cmd(cmd, timeout=180.0)
    finally:
        try:
            os.remove(tf_path)
        except OSError:
            pass


def call_claude(prompt: str) -> str:
    """Invoke Claude CLI as the Maestro / Synthesizer."""
    # Run claude in print mode with stdin redirected from /dev/null
    cmd = ["claude", "-p", prompt]
    return run_cmd(cmd, timeout=180.0, stdin_data="")


def main():
    parser = argparse.ArgumentParser(description="Multi-Model Debate: Gemini -> Grok -> Claude")
    parser.add_argument("topic", help="The architectural question, bug, or decision to debate")
    parser.add_argument("-o", "--output", help="Path to save markdown transcript", default=None)
    args = parser.parse_args()

    topic = args.topic.strip()
    print(f"\n[1/3] 🏛️ Gemini (المهندس المعماري) يطرح المقترح الأساسي للموضوع:\n{topic}...")

    p1 = f"""أنت المهندس المعماري للنظم (Software/Systems Architect).
الموضوع المطلوب تحليله وتقديم مقترح هندسي متكامل له:
{topic}

المطلوب:
1. صياغة القرار المعماري الأنسب ومقارنة الخيارات المطروحة مع ترميزها (O1, O2, O3).
2. تحديد المكونات التقنية والتنفيذية لكل مسار بوضوح.
3. تفصيل مصفوفة الإيجابيات والسلبيات والتعقيد والمخاطر.
اجعل الإجابة تقنية مباشرة، عميقة، بدون مقدمات إنشائية."""

    gemini_out = call_gemini(p1)
    if not gemini_out:
        gemini_out = "تعذر الحصول على رد من Gemini."
    print("✓ اكتمل مقترح Gemini.\n")

    print("[2/3] ⚡ Grok (محامي الشيطان) يهاجم المقترح ويصطاد الثغرات والافتراضات القاتلة...")
    p2 = f"""أنت محامي الشيطان (Devil's Advocate) ومهندس تدقيق نقدي صارم جداً.
الموضوع هو: {topic}

إليك مقترح المهندس المعماري:
{gemini_out}

مهمتك:
1. اصطياد كافة الفرضيات الساذجة، التكاليف الخفية، والعقبات التشغيلية في العالم الحقيقي.
2. تفنيد أرقام الأداء ونسب النجاح وإبراز نقاط الانهيار (Single Points of Failure).
3. استخراج الآثار الجانبية من الدرجة الثانية (Second-order consequences).
كن شرساً وموضوعياً، وفكك المقترح بنداً بنداً بدون مجاملة."""

    grok_out = call_grok(p2)
    if not grok_out:
        grok_out = "تعذر الحصول على رد من Grok."
    print("✓ اكتمل هجوم ونقد Grok.\n")

    print("[3/3] 🎯 Claude (المايسترو والحَكَم المستقل) يوازن النقدين ويصيغ الخطة النهائية...")
    p3 = f"""أنت رئيس المهندسين والمايسترو والحَكَم المستقل (Maestro & Independent Synthesizer).
أمامك مناظرة هندسية حول: {topic}

مقترح المهندس المعماري (الطرف الأول):
{gemini_out[:4000]}

نقد محامي الشيطان (الطرف الثاني):
{grok_out[:4000]}

مهمتك المحايدة:
1. التحكيم التقني: أين أصاب كل طرف وأين بالغ؟
2. جدول مقارنة نهائي بالمعايير الحاسمة (الجودة، التوافق، الأمان، التكلفة، الصيانة، الاعتمادية).
3. القرار التنفيذي النهائي: ما هو المسار الموصى به للمؤسسات والشركات، وما المسار للاستخدام الشخصي؟
اكتب الخلاصة بأسلوب احترافي مضاد للرصاص ومباشر بدون إنشائيات."""

    claude_out = call_claude(p3)
    if not claude_out:
        claude_out = "تعذر الحصول على رد من Claude."
    print("✓ اكتملت صياغة المايسترو (Claude).\n")

    md_transcript = f"""# محضر قاعة العمليات: مناظرة النماذج الذكية (Gemini vs Grok vs Claude)

**الموضوع**: {topic}

---

## 1. مقترح المهندس المعماري — Gemini
{gemini_out}

---

## 2. هجوم ونقد محامي الشيطان — Grok
{grok_out}

---

## 3. القرار النهائي والخطة المضادة للرصاص — المايسترو Claude
{claude_out}
"""

    if args.output:
        out_path = Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md_transcript, encoding="utf-8")
        print(f"تم حفظ المحضر كاملاً في: {out_path}\n")

    print("===============================")
    print("القرار النهائي والخطة (Claude Maestro):")
    print("===============================\n")
    print(claude_out)


if __name__ == "__main__":
    main()
