# Pragmatic UX Research, Hypothesis & Validation Kit

Operational guide for **Stages 1 & 7** of `system-ux`. Synthesizes Jeff Gothelf & Josh Seiden (*Lean UX*), Laura Klein (*Build Better Products*), Erika Hall (*Just Enough Research*), Leah Buley (*The UX Team of One*), David Travis & Philip Hodgson (*Think Like a UX Researcher*), Stephanie Marsh (*User Research*), Steve Krug (*Rocket Surgery Made Easy* & *Don't Make Me Think*), and Tom & David Kelley (*Creative Confidence*).

---

## 1. The Lean UX Discovery Block (Gothelf & Seiden + Klein)

Before proposing screens, fill out these 6 concise lines (compressed 8-Box Lean UX Canvas):

1. **Business Problem:** What concrete operational or product pain exists today? (No prescribed UI solution.)
2. **Measurable Outcome (Leading Indicator):** What user behavior changes if we succeed? (e.g., *cut invoice approval time from 4 min to < 45 s*, *reduce data-entry error rate by 50%*.)
3. **Target Archetypes (Proto-Personas):** Behavioral roles, goals, experience level (*perpetual intermediates* / *mainstreamers*), real-world constraints.
4. **User Outcome / Benefit:** What gets faster, safer, or less stressful for the user?
5. **Falsifiable Hypothesis Statement:**
   > *"We believe `[business outcome]` will be achieved if `[user archetype]` attains `[user benefit]` with `[UX approach/feature]`."*
6. **Riskiest Assumption & Cheapest Experiment:** What belief—if false—breaks the design? What is the smallest test to check it before full engineering?

**Klein's Analytics Rule:** Instrument the funnel steps and error events at design time (e.g., `flow_started`, `validation_error_field`, `flow_completed`, `undo_triggered`) so post-launch measurement tells you *where* friction happens, while qualitative testing tells you *why*.

---

## 2. Selecting the Right Research Method (Hall + Travis & Hodgson + Marsh + Buley)

Anchor every research choice to **Travis & Hodgson's Two Questions**:
- **Q1 (Discovery):** *"Who are our users and what are they actually trying to do?"* → **Field / Behavioral Research**.
- **Q2 (Evaluation):** *"Can people use what we designed to accomplish that goal?"* → **Usability Testing**.

### Fast Method Picker

| What You Need to Learn | Best Lightweight Method | Avoid / Anti-Pattern |
|---|---|---|
| Real goals, politics, constraints | **Stakeholder + Frontline Support Interviews** (Hall, Buley) | Only interviewing executives while ignoring operators/support staff. |
| Actual workflows & workarounds | **Contextual Inquiry / Episodic Interviews** (*"Walk me through the last time you did X"*) (Hall, Travis) | Asking *"Would you use feature X?"* or running **Focus Groups** (groupthink). |
| How users group concepts into nav | **Open / Closed Card Sorting** (Marsh, Userfocus) | Copying the backend database tables into sidebar tabs. |
| Whether navigation labels are findable | **Tree Testing** (Marsh) — text-only hierarchy test before visual UI | Guessing labels in a conference room. |
| First-impression clarity of a screen | **Five-Second Test** (Buley) — show screen 5s, ask *"What is this page for?"* | Asking *"Do you like the colors?"* |
| Uncovering usability flaws early | **Quick-and-Dirty Usability Test** with 3–5 users (Krug, Buley) | Waiting until post-launch or testing only with teammates who built it. |
| Blind-spot critique before code | **Heuristic Markup + Black Hat Session** (Buley, Nielsen) | Skipping critique because "it's just an MVP". |
| Quantifying live drop-off / variants | **Funnel Analytics + A/B Testing** (Klein, Hall, Marsh) | Running A/B tests before fixing broken usability (Design Darwinism). |

### Buley's "If You Can Only Do One Thing" Solo-Team Minimum
When shipping fast with a small engineering team, run at minimum:
1. **Proto-Personas** (15 min) + **One-Sentence UX Vision** (Userfocus)
2. **Object–Action Matrix & Task Flows** (30 min)
3. **Heuristic Markup + Black Hat Critique** (20 min)
4. **3-Participant Rapid Usability Test** on clickable prototype or staging build (1 morning)

---

## 3. Krug's Trunk Test (Navigation Orientation Gate)

Pick ANY deep internal route in the app (e.g., `/orders/4821/refund` or `/settings/webhooks/edit`), hide the URL bar, and verify a user can answer all **6 questions in <= 3 seconds**:
1. **What app/workspace is this?** (App/tenant identity)
2. **What page am I on?** (Clear, specific page title matching the link clicked)
3. **What are the major sections of this app?** (Persistent global navigation)
4. **What are my options at this level?** (Clear local tabs, sub-nav, or action bar)
5. **Where am I in the scheme of things?** (Active nav highlight + breadcrumbs at depth >= 2)
6. **How can I search / jump quickly?** (Visible Search or `⌘K` trigger)

Any "No" is an automatic **P1 Navigation Finding**.

---

## 4. Rocket Surgery Made Easy — 60-Minute DIY Usability Test Script (Krug)

**Cadence:** 3 participants in one morning (1 hour each + 10 min reset), engineering & product observe live, debrief immediately over lunch and pick the **top 3–5 most serious problems** to fix next sprint.

### Session Structure (60 Minutes)
1. **Welcome (4 min):**
   - Put participant at ease: *"We're testing the software, not you — you cannot do anything wrong. Be completely honest; you won't hurt anyone's feelings."*
   - Ask permission to record screen/audio (ethical consent — Marsh).
   - Explain **Think Aloud**: *"Tell me what you're looking at, what you're trying to do, and what you expect to happen."*
2. **Warm-Up Questions (2 min):**
   - Brief role & context questions (e.g., *"How often do you process orders in your day job? What tools do you use today?"*).
3. **Home / Main Screen Tour (3 min):**
   - Show the main screen without clicking yet: *"Just looking at this screen, what do you think this app does, and what would you click first?"*
4. **Realistic Scenario Tasks (35 min — 3 to 5 tasks):**
   - Write scenarios using **real-world user goals**, NEVER naming the UI buttons or menu labels!
   - *Bad task:* `"Click 'Billing', then click 'Create Credit Memo' and fill in amount."`
   - *Good task:* `"A customer called saying they were double-charged 250 MAD on order #1042 yesterday. Go ahead and fix their account."`
   - Stay strictly neutral. If stuck, prompt gently: *"What are you thinking right now?"* or *"What would you expect to find there?"*
5. **Probing (5 min):**
   - Revisit moments of hesitation, surprise, or confusion observed during tasks.
6. **Wrap-Up (5 min):**
   - Ask final open question (*"What was the single most frustrating part?"*), thank participant, stop recording.

### Krug's Repair Discipline
- **Focus ruthlessly on the most serious problems first** — ignore minor polish until P0/P1 blockers are fixed.
- **Take things away before adding things** — adding explanatory banners or extra buttons almost always makes a usability bug worse.
- **UX Detective Analysis (Travis & Hodgson):** Separate raw observed behavior (*"User clicked 'Export' looking for 'Print Invoice'"*) from hypothesis (*"Label ambiguity between Export and Print"*) before jumping to a redesign.

---

## 5. Usability Severity Decision Tree (Travis & Hodgson)

Classify every UX issue objectively — no opinion battles:

| Severity | Decision Criteria | Action Required |
|---|---|---|
| **P0 — Critical / Blocker** | Causes data loss, security/privacy error, irrecoverable failure, OR blocks a primary user task with no workaround. | **Hard stop.** Fix before shipping or sign-off. |
| **P1 — Serious** | High impact on frequent task OR affects > 30% of users; causes major delay, repeated slips/mistakes, broken Trunk Test, or severe accessibility block. | Fix in current sprint / before launch. |
| **P2 — Medium** | Moderate friction, minor excise, unclear secondary label, or workaround exists without major stress. | Schedule in backlog / next polish pass. |
| **P3 — Low / Cosmetic** | Rare edge case, minor alignment/wording tweak, zero task impact. | Fix opportunistically. |
