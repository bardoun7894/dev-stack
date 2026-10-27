# kb-dev invocation phrases and exclusions (moved from SKILL.md 2026-10-27)

## Invocation (English + Arabic)

| Trigger phrase (EN)                | Trigger phrase (AR)                          | What kb-dev does                                                  |
|------------------------------------|----------------------------------------------|-------------------------------------------------------------------|
| "new feature X"                    | "ميزة جديدة X" / "خاصية جديدة X"             | Run phases 0 → 2a → 4, pause for solo/fan-out decision            |
| "system design" / "design the system"| "تصميم النظام" / "معمارية النظام" / "صمم النظام قبل البناء" | Run `system-design` (phase 2c), then hard stop for D/Q approval |
| "build X" / "implement X"          | "ابني X" / "اعمل X" / "نفّذ X" / "صنع X"     | Run phases 0 → 12 (full pipeline)                                 |
| "implement the spec at specs/NNN"  | "نفّذ المواصفات في specs/NNN"                | Run phase 0, then jump to phase 5, then 6–12                      |
| "fix bug Y" (< 30 LOC)             | "أصلح خطأ Y" / "صلح Y" / "إصلاح Y"           | Run phase 0, then solo-mode phase 5a straight through to 12       |
| "are we drifting" / "direction"    | "هل انحرفنا عن الخطة"                        | Run `/direction` (drift.sh, one judge pass, report to `specs/_direction/`) |
| "retro the week" / after a long run| "راجع الأسبوع"                               | Run `/retro session`; human picks the fixes, never auto-apply     |
| "ship this branch"                 | "انشر هذا الفرع" / "إطلاق"                   | Run phases 9 → 12                                                 |
| "debug this"                       | "صحح هذا" / "ابحث عن المشكلة"                | Run `systematic-debugging` directly                               |
| "brainstorm X"                     | "فكّر في X" / "اقتراحات لـ X"                | Run `brainstorming` directly                                      |
| "spec out X" / "write a spec for X"| "اكتب مواصفات X" / "حدد X"                   | Run `kb-spec` standalone (phases 0,2,3,4 only — no implementation)|

**Language note:** I (Claude) understand Arabic natively. Even prompts in mixed Arabic/English/French route correctly based on semantic content, not just keyword matching. The hook regex covers the most common Arabic engineering vocabulary as a safety net.

Parked skills (`dogfood`, ...) are read from `~/.claude/skills-parked/<name>/SKILL.md`.

## What kb-dev explicitly does NOT do

- It does not rewrite `kb-spec`, `kb-query`, or any other sub-skill. It only sequences them.
- It does not replace `/speckit.*`. Spec Kit still owns spec/plan/tasks file authoring. kb-dev just wires the KB research steps before each Spec Kit call and the knowledge capture after.
- It does not silently run destructive operations. Merging, force-pushing, dropping migrations, deleting branches — all pause for user confirmation regardless of the current phase.

## Relationship to the standing-rule hook

The global `UserPromptSubmit` hook at `~/.claude/hooks/user-prompt-kb-check.sh` already reminds you to run `/kb-query` and `/kb-spec <phase>` before each matching action. kb-dev is the **explicit** codification of that rule as a complete skill — use it when the user wants "the whole pipeline" instead of cherry-picking phases manually.

