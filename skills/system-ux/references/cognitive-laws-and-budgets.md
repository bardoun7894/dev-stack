# Cognitive Laws, Psychological Bottlenecks & Engineering Budgets

Operational reference for **Stages 5 & 6** of `system-ux`. Synthesizes Don Norman (*The Design of Everyday Things*), Jeff Johnson (*Designing with the Mind in Mind*, 3rd Ed.), David C. Evans (*Bottlenecks*), Susan Weinschenk (*100 Things Every Designer Needs to Know About People*), Barry Schwartz (*The Paradox of Choice*), Jon Yablonski (*Laws of UX*), Ben Shneiderman (*Eight Golden Rules*), Jakob Nielsen (*10 Usability Heuristics*), and Userfocus (*Bright Ideas*).

---

## 1. Hard Numeric UX Budgets

Enforce these measurable biological and cognitive ceilings across every system app:

| Dimension | Hard Ceiling / Target | Source | Enforcement Tactic |
|---|---|---|---|
| **Direct manipulation / click response** | `<= 100 ms` (0.1 s) | Johnson Ch. 14 | Immediate active/pressed state, optimistic toggle, instant ripple/focus. |
| **Interactive pace (Doherty Threshold)** | `<= 400 ms` | Yablonski (*Laws of UX*) | Optimistic UI, client-side filtering/sorting for small lists, prefetched tabs. |
| **Uninterrupted train of thought** | `<= 1,000 ms` (1 s) | Johnson Ch. 14 | Render skeleton screen or inline spinner by `300ms` if response may exceed `400ms`. |
| **Focused unit-task wait ceiling** | `<= 10,000 ms` (10 s) | Johnson Ch. 14 | Determinate progress bar + step text + **Cancel** button for `1s–10s`. |
| **Long-running operations** | `> 10 s` → **Async** | Johnson + Cooper (Daemonic) | Move to background job with toast/job drawer + notification on completion; never freeze the screen. |
| **Working memory chunks** | `<= 4 items` | Weinschenk / Miller | Group forms, menus, nav sections, and KPI rows into chunks of 3–5 items; format numbers (`+212 612-345-678`). |
| **Simultaneous decision options** | `3–4` visible choices | Schwartz / Hick | Pre-select default; highlight 1 recommended option; hide long-tail options via progressive disclosure. |
| **Top-level navigation items** | `5–7` objects max | Rosenberg / Miller / IA | Fold sub-entities into parent Objects; move rare items to Settings. |
| **Navigation depth** | `<= 3 levels` | IA / Krug | Flat/two-level nav + contextual drawers; breadcrumbs always visible at depth >= 2. |
| **Grid columns (desktop workspace)** | `<= 3 primary columns` | Rosenberg Ch. 8 | e.g., Nav Rail + List/Main + Detail Inspector. Avoid 4+ competing panels. |
| **Touch / Click target size** | `>= 44×44 px` mobile; `>= 36×36 px` desktop | Johnson (Fitts) / WCAG | Adequate spacing (`>= 8px` gap) between adjacent destructive & safe actions. |
| **Sustained user attention span** | `7–10 min` | Weinschenk | Autosave drafts continuously; never lose work if user gets interrupted or steps away. |
| **Color contrast (WCAG AA)** | `>= 4.5:1` text; `>= 3:1` UI/icons | Johnson / Pickering | Never use color alone to signal status or errors; test protanopia/deuteranopia (~9% of men). |

---

## 2. Norman's Interaction Model & Error Proofing (*The Design of Everyday Things*)

### The 7 Fundamental Principles (Check Every Screen)
1. **Discoverability:** Looking at the screen reveals current state and available actions without guessing.
2. **Feedback:** Every user action produces immediate, unambiguous confirmation of the new state.
3. **Conceptual Model:** The visible *System Image* accurately teaches how objects and states work.
4. **Affordances:** Interactive elements look interactive; static elements look static.
5. **Signifiers:** Explicit cues (labels, icons, carets, active states) show *where* and *how* to act.
6. **Mappings:** Controls align spatially and logically with what they affect (e.g., row actions live on the row; filter controls sit directly above the list they filter).
7. **Constraints:** Prevent impossible actions using **logical** (disable/hide invalid actions with tooltip explaining why), **semantic** (date pickers that reject end < start), **cultural** (red = destructive, green = valid), and **physical** (input masks/types) constraints.

### Bridging the Two Gulfs
- **Gulf of Execution** (*"How do I achieve my goal?"*): Narrow via clear Main Instruction, Affordances, Signifiers, Mappings, and Constraints.
- **Gulf of Evaluation** (*"Did it work? What state is the system in now?"*): Narrow via immediate Feedback, visible system status, and clear Closure.

### 3 Levels of Processing
- **Visceral (0–2 s):** Clean visual hierarchy, breathing room, trustworthy aesthetic (*Aesthetic–Usability Effect*).
- **Behavioral (during work):** Zero friction, predictable idioms, responsive `< 100ms` feedback, keyboard speed.
- **Reflective (after work):** Pride/confidence in accurate results, auditability, zero regret (*Peak–End Rule*).

### Preventing Slips vs. Mistakes

| Error Class | Subtypes | Root Cause | System-App Prevention & Recovery |
|---|---|---|---|
| **Slips** *(Right goal, wrong execution)* | Capture, Description-Similarity, Mode-Error, Memory-Lapse | Distraction, similar adjacent buttons, hidden modes, multi-step recall | Visually separate destructive buttons from primary CTAs; eliminate invisible modes (or show glaring mode banner); **automate post-goal cleanup** (Johnson Ch. 8); provide **Undo** (`⌘Z` / toast undo); autosave drafts. |
| **Mistakes** *(Wrong goal or plan)* | Rule-Based, Knowledge-Based, Memory-Lapse | Flawed mental model, ambiguous labels, hidden consequences | Expose accurate Conceptual Model; show **live impact preview** before bulk/destructive actions (*"This will cancel 14 unpaid invoices and notify 12 customers"*); use clear plain-language labels instead of internal jargon. |

### Error Message Contract (*Bright Ideas* + Nielsen #9 + McKay)
Every error message MUST contain **three parts** and live right next to the user's foveal focus:
1. **What happened** (plain human language — zero raw stack traces, HTTP 500s, or DB keys).
2. **Why it happened** (specific constraint or cause, never blaming the user).
3. **Exact next step to fix it** (actionable button or concrete instruction).

> Bad: `Error 422: Invalid payload on field sku_id.`
> Good: `SKU "BLK-42" is already used by "Winter Jacket". Enter a unique SKU or open the existing product to edit it.`

---

## 3. Evans's 7 Psychological Bottlenecks Funnel (*Bottlenecks*)

Audit every core user journey sequentially from Bottleneck 1 → 7. **Never try to patch an early failure (e.g., bad perception) with a late tactic (e.g., gamification).**

1. **Attention (Getting Noticed):**
   - Respect **foveal acuity** (high resolution is tiny; place alerts/errors right beside the control being edited, not in a distant corner).
   - Match **Task-Positive** users (goal-driven ops → strip distractions, surface search/filters/CTAs) vs. **Task-Negative** users (browsing/exploring → rich visual overview & curated entry points).
2. **Perception (Understood Instantly):**
   - Apply **all 7 Gestalt principles** (Proximity, Similarity, Continuity, Closure, Symmetry, Figure/Ground, Common Fate) and check for *accidental* false groupings.
   - Use subtle elevation/depth and purposeful motion (`150–250ms` ease-out) to explain spatial transitions.
3. **Memory (Retained & Filtered):**
   - Protect **working memory** (keep context visible in drawers/headers so users never memorize IDs across pages).
   - Apply **Signal Detection Theory:** Visually separate true high-priority **signals** (failed payment, SLA breach) from low-priority **noise** (routine sync logs) to avoid alert fatigue and missed critical events.
   - Tie new concepts to existing mental schemas (recognition over recall).
4. **Disposition (Resonating with the Role):**
   - Match tone, density, and language to the user's real role, stress level, and core need (safety, accuracy, speed, status).
5. **Motivation (Sustained Engagement):**
   - Use **Escalating Commitment** in onboarding (deliver value in 60 seconds before asking for heavy setup or billing).
   - Resolve **Approach–Avoidance Conflict** at commitment points (show exact cost, preview, reversibility, and privacy assurance right beside the Submit/Pay/Publish button).
   - Leverage the **Goal-Gradient Effect** (visible step progress accelerates completion).
6. **Social Influence (Team & Org Trust):**
   - Show authentic attribution (*"Approved by Sara · 2m ago"*), transparent audit logs, and constructive collaboration cues.
7. **Receptivity (Adoption & Advocacy):**
   - Earned automatically only when Bottlenecks 1–6 pass cleanly.

---

## 4. Load Hierarchy & Perceptual Laws (Weinschenk + Johnson + Yablonski)

### Weinschenk's Load Hierarchy (Trade Downward!)
```
MOST EXPENSIVE:   1. Cognitive Load  (thinking, deciding, remembering, calculating)
                  2. Visual Load     (scanning dense clutter, decoding poor typography)
LEAST EXPENSIVE:  3. Motor Load      (clicking a clear button, scrolling, tapping)
```
**Rule:** Always spend cheap **motor load** (an extra obvious step or click — Krug's 2nd Law) to save expensive **cognitive load**. Never pack 15 confusing controls into one screen just to boast "fewer clicks".

### Perceptual & Motor Laws
- **Jakob's Law:** Users spend 99% of their time in other apps. Adopt familiar conventions (top-left logo = home, top-right = profile/settings, `⌘K` = command palette, `Esc` = close) unless you have overwhelming proof a novel pattern beats convention.
- **Fitts's Law:** Big, close targets are fast and accurate; tiny, distant targets cause slips. Place primary actions right where the user's hand/cursor finishes the task.
- **Steering Law:** Avoid nested hover-only cascading menus (narrow horizontal corridors force slow, error-prone mouse steering); use click-to-open panels or flat mega-menus instead.
- **Von Restorff (Isolation) Effect:** Exactly **ONE** primary visual CTA per screen/dialog so the user's eye lands on it effortlessly.
- **Peak–End Rule:** Users remember the **most intense moment** (e.g., resolving a critical alert or seeing an instant report) and the **ending** (explicit confirmation, summary, and clear next action). Never end a major workflow with a blank white screen or silent redirect.
- **Tesler's Law (Conservation of Complexity):** Irreducible domain complexity exists—push it into smart backend logic, defaults, and validation rather than dumping it onto the user.
- **Postel's Law:** Be liberal in what input formats you accept from humans; be strict, clean, and predictable in what the system outputs.

---

## 5. Quick Cross-Check: Nielsen's 10 Heuristics & Shneiderman's 8 Golden Rules

| ID | Principle | Quick Pass Check |
|---|---|---|
| **H1 / G3** | Visibility of System Status & Informative Feedback | Does every action respond in `< 100ms`, every wait > 400ms show progress, and current location/mode stay obvious? |
| **H2** | Match System to Real World | Are 100% of labels in the user's domain language (zero DB/API jargon, natural workflow order)? |
| **H3 / G6–7** | User Control, Freedom, Easy Undo & Internal Locus | Can the user cancel, go back, undo mistakes, and never feel hijacked by unexpected system jumps? |
| **H4 / G1** | Consistency & Standards | Do identical actions behave identically across all objects (Semantic IxD verb symmetry) and follow platform idioms? |
| **H5 / G5** | Error Prevention | Do constraints, defaults, and live previews stop slips and mistakes *before* submission? |
| **H6 / G8** | Recognition Rather Than Recall | Are options, active filters, and parent context visible instead of memorized across screens? |
| **H7 / G2** | Flexibility, Universal Usability & Accelerators | Are mainstream workflows effortless while frequent operators get keyboard shortcuts, bulk actions, and saved views? |
| **H8** | Aesthetic & Minimalist Design | Does every element pass McKay's 4-Question Audit and Krug's 3rd Law (zero decorative noise)? |
| **H9** | Recognize, Diagnose, Recover from Errors | Does every error follow the 3-part Contract (what, why, exact fix) next to the offending control? |
| **H10 / G4** | Task-Focused Help & Dialog Closure | Does every multi-step flow end with explicit closure, and is contextual help embedded at the point of need? |
