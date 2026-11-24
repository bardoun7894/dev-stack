---
name: system-ux
description: System app UX, IA, user flows, forms & UX audits (auto-fires before UI code). Use proactively for any new system app, SaaS, admin panel, ERP/CRM, dashboard, multi-step workflow, form, or UX audit—synthesizing all 23 IxDF UX books + 7 specialty classics into a 7-stage pipeline. Triggers on "system ux", "design the ux", "ux architecture", "user flow", "information architecture", "ux audit", "make it intuitive", "reduce friction", "/system-ux", and Arabic/Darija "تجربة المستخدم", "تصميم تجربة المستخدم", "UX للتطبيق", "هندسة تجربة المستخدم", "مسار المستخدم".
---

# system-ux — Book-Grounded UX Architecture for System Applications

Design system applications (SaaS, ops panels, dashboards, ERP/CRM, internal tools, web/mobile apps) from cognitive science and interaction grammar — **before** wireframing or coding UI. Built on deep synthesis of **all 23 books from the IxDF UX Design Books Guide** plus **7 canonical UX specialty frameworks** (30 sources total; see `references/book-canon.md`).

> **Core Principle:** Never mirror the database schema or backend API in the UI (*implementation model*). Derive the smallest, most symmetrical **Conceptual Model (Objects × Actions × Attributes)** that fits the user's **mental model**, eradicate **excise**, design each screen as an **inductive conversation**, and enforce measurable **cognitive, latency, and error budgets**.

## Automatic Invocation (Standing Rule)

**`system-ux` auto-fires — do not wait for `/system-ux`:**
- **New system app / site / product** → auto-runs **Mode A** (`specs/NNN/ux-architecture.md` + `check.sh --lite|--full`, owner approves Object–Action Matrix & `UX-D` codes) in `kb-dev` Phase 2c alongside `system-design`, before `/kb-spec plan` or any UI code.
- **New screen, module, dashboard, form, or multi-step workflow in an existing app** → auto-runs **Mode B (Feature UX Delta)** silently before `frontend-design` or writing UI components.
- **User reports confusion, high friction, or asks to review/audit UX** → auto-runs **Mode C (10-Point UX Audit)**.
- **Skip ONLY when:** FAST LANE tiny change (`<= 20` lines: copy/color/config tweak) or pure backend/infra change with zero user-facing UI.

## When to Use — and When NOT to Use

**Use `system-ux` when:**
- Designing UX for a **new system app** (`specs/NNN/ux-architecture.md` — runs alongside or right before `system-design`, and before `frontend-design` / `design-md` / implementation).
- Designing a **new module, workflow, form, or complex view** inside an existing app (Mode B: Feature UX Delta).
- Auditing an **existing app or screen** suffering from user confusion, high drop-off, support tickets, bloated menus, or "engineers built it from the DB tables" smell (Mode C: UX Audit).

**Do NOT use `system-ux` for:**
- Pure visual restyling, color themes, or brand aesthetics → use `design-md`, `design-check`, `normalize`, `polish`, or `unslop`.
- Backend infrastructure, hosting, or database topology → use `system-design`.
- Pure accessibility/Lighthouse code lint → use `audit` (after `system-ux` + build).

## Files in This Skill

| Path | Load when... |
|---|---|
| `references/book-canon.md` | Core UX foundations, product strategy, UI design & interaction patterns (IxDF Books 1–15). |
| `references/book-canon-research-and-classics.md` | UX research methods, psychological bottlenecks, *About Face*, and 7 specialty classics (Books 16–30). |
| `references/semantic-ixd-and-patterns.md` | Building the Object-Action Matrix, choosing Application Posture, applying Remove/Organize/Hide/Displace, selecting Tidwell UI patterns, designing forms, or applying McKay's Inductive UI & Control Body Language. |
| `references/cognitive-laws-and-budgets.md` | Checking numeric thresholds (0.1s/0.4s/1s/10s responsiveness, 4-item working memory, 3–4 choice cap), Norman's 7 Principles & Slips/Mistakes, Evans's 7 Psychological Bottlenecks, Gestalt, Fitts/Steering Laws, Nielsen 10, Shneiderman 8. |
| `references/research-and-validation.md` | Writing Lean UX hypotheses, choosing research methods (Hall, Buley, Travis & Hodgson, Marsh), running a Trunk Test, or generating a Rocket Surgery 60-min usability test script. |
| `references/template.md` | Authoring `specs/NNN/ux-architecture.md` (LITE or FULL). |
| `references/checklist.md` | Running the 10-point Pre-Build / Pre-Ship UX Audit (P0–P3 scoring). |
| `scripts/check.sh` | Zero-AI gate verifying `ux-architecture.md` completeness (`--lite` or `--full`). |

## Pick the Mode

| Mode | When | Deliverable |
|---|---|---|
| **A. New System App (`--lite` / `--full`)** | New app or major system redesign (`LITE` = single role, <= 6 core objects; `FULL` = multi-role, complex workflows, dashboards/forms/mobile). | `specs/NNN/ux-architecture.md` validated by `scripts/check.sh`. |
| **B. Feature / Module UX Delta** | Adding a feature/screen to an existing app. | Concise UX delta: Lean Hypothesis + Object-Action Delta + Task Flow + Inductive Screen Spec + Edge/Error States. |
| **C. Existing App UX Audit** | Reviewing live code, screens, or mockups for friction. | P0–P3 scored report using `references/checklist.md` (Trunk Test, Excise Audit, 4-Question Communication Audit, Psychological Bottlenecks, Nielsen/Norman/Shneiderman). |

---

## The 7-Stage System-App UX Pipeline

Execute stages sequentially for **Mode A**. For **Mode B**, run Stages 1, 3, 4, 5, 6 as a tight delta. For **Mode C**, run `references/checklist.md` against the existing app and map every finding to its broken principle + concrete fix.

### Stage 1 — Outcomes, Users & Hypotheses
*Sources: Lean UX (Gothelf & Seiden), Build Better Products (Klein), Just Enough Research (Hall), Think Like a UX Researcher (Travis & Hodgson), UX Team of One (Buley), Elements of UX (Garrett).*

1. **Outcome over Output:** State the measurable user behavior change and business metric — never just "build screen X".
2. **Behavioral Archetypes (not demographics):** Define 1–3 role archetypes with primary **goals** (the *why*, not tasks), **experience level** (design for Cooper's *perpetual intermediates* and Colborne's *mainstreamers*, not vocal edge-case experts), and **context of use** (interruptions, device, stress, Arabic/RTL or bilingual needs).
3. **Falsifiable Hypothesis Statement:**
   > *"We believe `[business outcome]` will be achieved if `[user archetype]` attains `[user outcome]` with `[UX approach]`."*
4. **Riskiest Assumption & Minimal Evidence:** Name the single riskiest UX assumption and the cheapest test to validate it (`references/research-and-validation.md`).

### Stage 2 — Application Posture & Conceptual Model
*Sources: About Face (Cooper et al.), The Design of Everyday Things (Norman), User Friendly (Kuang & Fabricant), UX for Beginners (Marsh).*

1. **Declare Application Posture** per major surface (`references/semantic-ixd-and-patterns.md`):
   - **Sovereign** (long focused work: ERP, IDE, ops console) → maximize canvas, calm visual chrome, keyboard shortcuts, modeless feedback, perpetual-intermediate density.
   - **Transient** (short single task: quick add, approval modal, scanner, checkout) → oversized obvious controls, explicit verb-object labels, zero deep menus, fast exit.
   - **Daemonic** (background sync, watchers, notifications) → zero routine UI; transient config only when required.
2. **Conceptual Model ≠ Implementation Model:** Map the user's real-world mental model to the **System Image**. Never leak raw DB tables, foreign keys, internal statuses, or microservice names into user labels.
3. **Idioms over Forced Metaphors:** Prefer standard learn-once UI idioms (master-detail, inline edit, command palette, tabs, chips) over strained physical metaphors.
4. **Ethical Agency Check:** Ensure design widens user control — zero dark patterns, fake urgency, or compulsive loops (*User Friendly*, *UX Magic* Ch. 7, *Laws of UX*).

### Stage 3 — Semantic Grammar & Information Architecture
*Sources: UX Magic (Rosenberg), Information Architecture (Rosenfeld, Morville & Arango), Simple and Usable (Colborne), The Paradox of Choice (Schwartz).*

**Complete this BEFORE drawing a single wireframe:**
1. **Object–Action–Attribute Matrix (Semantic IxD Layer 1):**
   - List the **minimum set of core Domain Objects (Nouns)** (aim for <= 7 top-level objects).
   - List **universal Actions (Verbs)** that work **symmetrically** across objects (e.g., Filter, Search, Create, Edit, Archive, Export behave identically everywhere → *linear cognitive load*).
   - List **key Attributes (Adjectives)** and mark which are *Summary* (shown in lists/cards) vs *Detail* (shown in inspector/detail view) vs *Filterable*.
2. **Colborne's 4 Simplification Moves** applied to every feature request:
   - **Remove** weak/rare features, redundant fields, and unnecessary choices.
   - **Organize** remaining items into hard-edged, non-overlapping groups (chunk to <= 4–5 items per group; obey Miller's Law & Paradox of Choice).
   - **Hide** expert/rare controls via progressive or staged disclosure with clear discovery cues.
   - **Displace** complexity to the right device/surface or let the system automate it (Tesler's Law).
3. **IA Four Systems:** Specify **Organization** (navigation tree, depth <= 3), **Labeling** (user vocabulary, verb-first actions, noun-first sections), **Navigation** (global, local, contextual, breadcrumbs — must pass Krug's **Trunk Test**), and **Search/Filter** (never use search as a crutch for broken browsing).

### Stage 4 — Task Flows & Excise Eradication
*Sources: About Face (Cooper), UX Magic (Rosenberg), Don't Make Me Think (Krug), Designing Interfaces (Tidwell et al.), Shneiderman's Eight Golden Rules.*

1. **Map Critical User Flows** (Mermaid flowchart) showing Entry Point → Happy Path → Recovery/Escape Hatch → Closure.
2. **Eradicate All 4 Types of Excise:**
   - **Navigation excise:** collapse unnecessary page jumps; use Master-Detail / Split View, drawers, or inline actions that inherit object context.
   - **Modal/interruption excise:** ban "stopping the proceedings with idiocy" — replace trivial confirmation dialogs with **Undo** (`⌘Z` / toast undo); reserve blocking modals only for irreversible destructive actions.
   - **Visual/form excise:** eliminate redundant re-entry, manual formatting, and welded-on onboarding wizards that can't be dismissed.
   - **Choice excise:** pick smart defaults for 80% of users (satisficers); cap visible simultaneous choices to 3–4 where possible.
3. **Apply Krug's 3 Laws:** Make every click mindless and unambiguous (2nd Law), and cut copy in half, then cut it in half again (3rd Law).
4. **Inflect for Frequency:** High-frequency actions are 1 click / keyboard shortcut away; rare admin actions live in overflow/settings.

### Stage 5 — Screen Layout, Inductive Communication & UI Patterns
*Sources: UI is Communication (McKay), Designing Interfaces 3rd Ed. (Tidwell, Brewer & Valencia), Web Form Design (Wroblewski), Designing with the Mind in Mind (Johnson), 100 Things (Weinschenk), Inclusive Design Patterns (Pickering).*

For every key screen, specify:
1. **Inductive Main Instruction:** One explicit headline/purpose answering *"What am I supposed to do here?"* (never vague headers like "Manage" or "Dashboard"). Every element on screen must serve this instruction.
2. **Semantic Grid & Screen Archetype:** Pick a proven Tidwell/Rosenberg pattern (`Overview / Focus / Make / Do` — e.g., Two-Panel Master-Detail, List + Slide-Over Inspector, Canvas + Palette, Staged Wizard, Dashboard with Small Multiples). Keep layout consistent across objects (Spatial Memory).
3. **Control Body Language & Form Discipline:**
   - Match control to semantics (checkbox = single on/off; radio = 2–5 mutually exclusive visible options; select/combobox = > 5 options; primary button = 1 clear verb-object CTA; link = navigation).
   - Forms: **single-column**, top-aligned labels, proportional field widths, forgiving input formats (Postel's Law), smart prefills/defaults, inline validation on blur/fix (never premature red before typing finishes), clear required/optional marking.
4. **Perceptual & Cognitive Guardrails:**
   - **Gestalt check:** Proximity, Similarity, Figure/Ground, Common Fate — verify zero accidental groupings.
   - **Fitts's & Steering Laws:** Large, easy-to-hit touch/click targets (>= 44×44px mobile, >= 36px desktop), primary CTA near user's current eye/hand focus, zero fragile cascading hover flyouts.
   - **Color & Peripheral Vision:** Never encode status/error by color alone (pair with icon + text); place feedback right next to the control where foveal vision already rests.
   - **Load Hierarchy (Weinschenk):** Always trade cheap *motor* effort (an extra obvious click) to eliminate expensive *cognitive* load (guessing, calculating, remembering across screens).
   - **Inclusive & Bilingual/RTL Ready:** Native semantic HTML, full keyboard navigation, logical CSS properties (`margin-inline`, `text-align: start`) so Arabic/RTL works natively without visual breakage.
5. **McKay's 4-Question Element Audit:** For every control/text block, verify: *Why is it here? What does it communicate? Would another control communicate better? What is lost if removed?*

### Stage 6 — Psychological Bottlenecks, Error Proofing & Latency Budgets
*Sources: Bottlenecks (Evans), The Design of Everyday Things (Norman), Designing with the Mind in Mind (Johnson), Laws of UX (Yablonski), Bright Ideas (Userfocus).*

1. **7-Stage Psychological Bottlenecks Check (Evans):** Verify the core flow clears: *Attention* (foveal cue) → *Perception* (instant Gestalt affordance) → *Memory* (zero cross-screen recall, signal vs noise) → *Disposition* (fits role/context) → *Motivation* (Goal-Gradient progress, intrinsic mastery/autonomy) → *Social* (trust/credibility cues) → *Receptivity*.
2. **Error Prevention & Recovery Matrix (Norman + Bright Ideas):**
   - Prevent **Slips** (distinct controls, eliminate hidden modes, constrain inputs, undo).
   - Prevent **Mistakes** (accurate conceptual model, previews before bulk/destructive actions, live impact counts).
   - **Error Message Contract:** Every error states (1) *what happened* in plain user language, (2) *why*, and (3) *exact next action to fix it* — zero raw error codes, zero blame.
3. **Responsiveness & Perceived Latency Budgets (Johnson + Doherty Threshold):**
   - `<= 100 ms`: Direct manipulation, button press, hover, toggle feedback (cause-and-effect).
   - `<= 400 ms`: Doherty Threshold — keep interactive transitions/filters under 400 ms or use optimistic UI.
   - `400 ms – 1 s`: Show subtle inline busy/skeleton state; preserve user's train of thought.
   - `1 s – 10 s`: Determinate progress indicator + explain what is happening + allow cancel.
   - `> 10 s`: Asynchronous background job (Daemonic posture) with notification + resume link so user is never trapped.
4. **Empty, Loading, Partial, Error & Peak-End States:** Define all 5 UI states for every screen and intentionally craft the **Peak** (moment of highest value) and **End** (clear closure + next logical step).

### Stage 7 — Validation Plan, Gate & Owner Sign-Off
*Sources: Rocket Surgery Made Easy (Krug), Think Like a UX Researcher (Travis & Hodgson), User Research (Marsh), Nielsen's 10 Heuristics.*

1. **Write Concrete Validation Tasks:** 3–5 realistic scenario tasks (no UI jargon, no hints) ready for a 3-participant DIY usability test (`references/research-and-validation.md`) + Trunk Test check on every deep route.
2. **Run the Gate (Mode A):**
   ```bash
   bash ~/.claude/skills/system-ux/scripts/check.sh specs/NNN/ux-architecture.md --lite|--full
   ```
   Walk `references/checklist.md` and fix any P0/P1 findings until `check.sh` exits `0`.
3. **HARD STOP (for New System App Mode A):** Present the **Object-Action Matrix**, **Posture**, **UX Decisions (`UX-D1..N`)**, and **Open Questions (`UX-Q1..N`)** to the owner for explicit approval before moving to UI implementation (`design-md` / `frontend-design` / `kb-dev`).

---

## Handoffs to Companion Skills

- **Before `system-ux`:** `office-hours` or `brainstorming` (product WHY), `kb-query` (prior decisions).
- **Alongside `system-ux`:** `system-design` (technical architecture), `arabic-ui` (when UI copy is Arabic/RTL).
- **After `system-ux` approval:** `design-md` / `dribbble-design` (visual language) → `frontend-design` (build) → `clarify` (microcopy) → `harden` (edge cases) → `polish` → `audit` / `dogfood` (live verification).
