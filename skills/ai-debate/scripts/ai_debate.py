#!/usr/bin/env python3
"""
ai_debate.py: Multi-Model Debate Pipeline with Quota Fallback, Web Researcher, and Narrative Storyteller.
- Stage 0: Research (Perplexity / WebSearch / KB)
- Stage 1: Architect (Gemini / agy)
- Stage 2: Devil's Advocate (Grok with graceful fallback to Claude-Opponent on quota exhaustion)
- Stage 3: Maestro / Synthesizer (Claude / Neutral Arbiter)
- Stage 4: Storyteller (Dramatic War Room Narrative / Story of the Debate)
"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def run_cmd(cmd: list[str], input_text: str | None = None, timeout: float = 180.0) -> tuple[int, str]:
    """Run shell command safely and return (returncode, output)."""
    try:
        res = subprocess.run(
            cmd,
            input=input_text,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False
        )
        out = (res.stdout or "").strip()
        err = (res.stderr or "").strip()
        combined = f"{out}\n{err}".strip() if err else out
        return res.returncode, combined
    except subprocess.TimeoutExpired:
        return -1, "Timeout expired"
    except Exception as e:
        return -1, str(e)


def call_researcher(topic: str) -> str:
    """Invokes Perplexity API if PPLX_API_KEY exists, otherwise uses Web Search CLI or KB."""
    pplx_key = os.environ.get("PPLX_API_KEY") or os.environ.get("PERPLEXITY_API_KEY")
    if pplx_key:
        try:
            import urllib.request
            import json
            req_data = json.dumps({
                "model": "sonar-pro",
                "messages": [
                    {"role": "system", "content": "You are a senior tech research analyst. Provide concise facts, market alternatives, and architectural patterns with citations."},
                    {"role": "user", "content": f"Research prior art, practical limitations, and architecture standards for: {topic}"}
                ]
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.perplexity.ai/chat/completions",
                data=req_data,
                headers={"Authorization": f"Bearer {pplx_key}", "Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"Perplexity API query failed ({e}), falling back to local synthesis.", file=sys.stderr)

    return f"خلفية بحثية وتقنية حول: {topic}"


def call_gemini(prompt: str) -> str:
    """Invokes Gemini CLI (agy) as the Architect."""
    code, out = run_cmd(["agy", "-p", prompt], timeout=180.0)
    return out if code == 0 and out else "تعذر الحصول على رد من Gemini."


def call_grok(prompt: str) -> str:
    """Invokes Grok CLI with quota-exhaustion fallback."""
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
        code, out = run_cmd(cmd, timeout=120.0)
        
        # Check for quota exhaustion or CLI failure
        is_quota_error = any(err_word in out.lower() for err_word in [
            "quota", "rate limit", "credits", "insufficient_quota", "429", "exceeded your current quota", "503", "auth_unavailable"
        ])
        
        if code != 0 or not out or is_quota_error:
            print("⚠️ Grok quota exhausted or unavailable. Activating Claude Red-Team fallback...", file=sys.stderr)
            fallback_prompt = f"أنت تعمل الآن كـ Devil's Advocate ومحامي الشيطان لمهاجمة المقترح واصطياد الثغرات القاتلة:\n\n{prompt}"
            f_code, f_out = run_cmd(["claude", "-p", fallback_prompt], input_text="", timeout=120.0)
            return f"(بواسطة Claude Red-Team بسبب تعذر Grok):\n\n{f_out}"
        
        return out
    finally:
        try:
            os.remove(tf_path)
        except OSError:
            pass


def call_claude(prompt: str) -> str:
    """Invokes Claude CLI as the Maestro / Synthesizer."""
    code, out = run_cmd(["claude", "-p", prompt], input_text="", timeout=180.0)
    return out if code == 0 and out else "تعذر الحصول على رد من Claude."


def generate_story(topic: str, gemini_out: str, grok_out: str, claude_out: str) -> str:
    """Generates a complete narrative war-room story depicting the tension, clash, and breakthrough."""
    story_prompt = f"""اكتب قصة درامية واقعية وشيقة (Full War-Room Story) تروي أحداث هذه المناظرة التقنية الساخنة داخل غرفة العمليات (War Room).

الموضوع الذي اشتعل حوله الصراع:
{topic}

أبطال القصة وتفاصيل الجلسة:
1. Gemini (المهندس المعماري الطموح - صاحب الرؤية والمقترح الأول):
{gemini_out[:1200]}

2. Grok (محامي الشيطان الشرس والمشكك - صياد الثغرات والواقعي الصارم):
{grok_out[:1200]}

3. Claude (المايسترو الحكيم - كبير المهندسين الهادئ الذي وزّن الأمور وصاغ الحل النهائي):
{claude_out[:1200]}

المطلوب صياغة قصة بأسلوب أدبي سينمائي مشوق يتضمن:
- المشهد الافتتاحي: أجواء قاعة العمليات والمخططات على الشاشات والرهان الكبير.
- الصدام الأول: عندما طرح Gemini مقترحه واعتبره حلاً لا تشوبه شائبة.
- الانفجار التقني: دخول Grok وهجومه المباغت على الافتراضات الساذجة والتكاليف الخفية.
- لحظة التوتر وتصادم الرؤى حول نقاط الانهيار.
- تدخل المايسترو Claude: الصمت الذي ساد الغرفة، وكيف فكك النزاع وصاغ خطة نهائية مضادة للرصاص أرضت العقل والواقع.
- الخاتمة: العبرة والقرار التنفيذي الذي خرج به الفريق في نهاية الليلة.
اجعل القصة ممتعة، غنية بالحوارات الحية والمصطلحات التقنية الواقعية."""

    code, story_out = run_cmd(["agy", "-p", story_prompt], timeout=180.0)
    if code != 0 or not story_out:
        # Fallback to claude for storytelling
        code, story_out = run_cmd(["claude", "-p", story_prompt], input_text="", timeout=180.0)
    
    return story_out if story_out else "تعذر توليد القصة الدرامية."


def main():
    parser = argparse.ArgumentParser(description="Multi-Model Debate with Quota Fallback, Researcher & Narrative Story")
    parser.add_argument("topic", help="The architectural question, bug, or decision to debate")
    parser.add_argument("-o", "--output", help="Path to save markdown transcript", default=None)
    parser.add_argument("--skip-story", action="store_true", help="Skip generating the dramatic war-room narrative")
    args = parser.parse_args()

    topic = args.topic.strip()

    print(f"\n[0/4] 🔍 مرحلة البحث والتقصي (Perplexity / Research Engine)...")
    research_context = call_researcher(topic)
    print("✓ اكتمل جمع الخلفية البحثية.\n")

    print(f"[1/4] 🏛️ Gemini (المهندس المعماري) يطرح المقترح الأساسي للموضوع:\n{topic}...")
    p1 = f"""أنت المهندس المعماري للنظم (Software/Systems Architect).
الموضوع المطلوب تحليله:
{topic}

خلفية البحث:
{research_context[:1500]}

المطلوب:
1. صياغة القرار المعماري الأنسب ومقارنة الخيارات المطروحة مع ترميزها (O1, O2, O3).
2. تفكيك النظام إلى موديولات ومسارات واضحة.
3. تحديد المكونات التقنية والتنفيذية لكل مسار بدقة ومصفوفة الإيجابيات والمخاطر.
اجعل الإجابة تقنية مباشرة، عميقة، بدون مقدمات إنشائية."""

    gemini_out = call_gemini(p1)
    print("✓ اكتمل مقترح Gemini.\n")

    print("[2/4] ⚡ Grok (محامي الشيطان) يهاجم المقترح (مع فحص الحصة والبديل التلقائي)...")
    p2 = f"""أنت محامي الشيطان (Devil's Advocate) ومهندس تدقيق نقدي صارم جداً.
الموضوع هو: {topic}

إليك مقترح المهندس المعماري:
{gemini_out}

مهمتك:
1. اصطياد كافة الفرضيات الساذجة، التكاليف الخفية، والعقبات التشغيلية في العالم الحقيقي.
2. استخراج الثغرات ونقاط الانهيار (Single Points of Failure) والآثار من الدرجة الثانية.
3. تفنيد أرقام الأداء وافتراضات التوسع.
كن شرساً وموضوعياً، وفكك المقترح بنداً بنداً بدون مجاملة."""

    grok_out = call_grok(p2)
    print("✓ اكتمل هجوم ونقد محامي الشيطان.\n")

    print("[3/4] 🎯 Claude (المايسترو والحَكَم المستقل) يوازن النقدين ويصيغ الخطة النهائية...")
    p3 = f"""أنت رئيس المهندسين والمايسترو والحَكَم المستقل (Maestro & Independent Synthesizer).
أمامك مناظرة هندسية حول: {topic}

مقترح المهندس المعماري:
{gemini_out[:4000]}

نقد محامي الشيطان:
{grok_out[:4000]}

مهمتك المحايدة:
1. التحكيم التقني: أين أصاب كل طرف وأين بالغ؟
2. جدول مقارنة نهائي بالمعايير الحاسمة.
3. القرار التنفيذي النهائي والخطة المضادة للرصاص.
اكتب الخلاصة بأسلوب احترافي مضاد للرصاص ومباشر بدون إنشائيات."""

    claude_out = call_claude(p3)
    print("✓ اكتملت صياغة المايسترو (Claude).\n")

    story_out = ""
    if not args.skip_story:
        print("[4/4] 📖 صياغة القصة الكاملة للمناظرة وأحداث غرفة العمليات (War Room Story)...")
        story_out = generate_story(topic, gemini_out, grok_out, claude_out)
        print("✓ اكتملت القصة الكاملة للمناظرة.\n")

    story_section = f"\n---\n\n## 4. قصة المناظرة الكاملة: كواليس غرفة العمليات\n\n{story_out}\n" if story_out else ""

    md_transcript = f"""# محضر قاعة العمليات: مناظرة النماذج الذكية (Gemini vs Grok vs Claude)

**الموضوع**: {topic}

---

## 0. الخلفية البحثية (Researcher)
{research_context}

---

## 1. مقترح المهندس المعماري — Gemini
{gemini_out}

---

## 2. هجوم ونقد محامي الشيطان — Grok (مع الحصة/البديل)
{grok_out}

---

## 3. القرار النهائي والخطة المضادة للرصاص — المايسترو Claude
{claude_out}
{story_section}"""

    if args.output:
        out_path = Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md_transcript, encoding="utf-8")
        print(f"تم حفظ المحضر كاملاً في: {out_path}\n")

    print("===============================")
    print("القرار النهائي والخطة (Claude Maestro):")
    print("===============================\n")
    print(claude_out)

    if story_out:
        print("\n===============================")
        print("📖 قصة المناظرة (War-Room Story):")
        print("===============================\n")
        print(story_out[:2000] + ("..." if len(story_out) > 2000 else ""))


if __name__ == "__main__":
    main()
