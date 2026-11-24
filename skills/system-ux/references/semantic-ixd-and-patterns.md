# Semantic IxD, Posture, Information Architecture & UI Patterns

Operational handbook for **Stages 2, 3, 4, and 5** of `system-ux`. Synthesizes Daniel Rosenberg (*UX Magic*), Alan Cooper et al. (*About Face*), Giles Colborne (*Simple and Usable*), Everett McKay (*UI is Communication*), Jenifer Tidwell et al. (*Designing Interfaces*, 3rd Ed.), Rosenfeld/Morville/Arango (*Information Architecture*), Luke Wroblewski (*Web Form Design*), and Heydon Pickering (*Inclusive Design Patterns*).

---

## 1. Application Posture Selection (Cooper — *About Face*)

Choose the posture for each major surface **before** choosing layouts or navigation:

| Posture | When to Use | Layout & Chrome Rules | Interaction Rules |
|---|---|---|---|
| **Sovereign** | Users live inside the app for 20+ min sessions (ERP, CRM, admin console, IDE, dispatch board, analytics workspace). | Full-viewport canvas; muted/neutral chrome so data dominates; persistent sidebar/header; calm visual density suited for *perpetual intermediates*. | Modeless inline feedback (toasts/status bar, not popups); keyboard shortcuts & command palette (`⌘K`); rich Undo; preserve scroll/filter state across views. |
| **Transient** | Single focused job in < 2 min (quick create, approval dialog, barcode scan, checkout, password reset, mobile companion). | High-relief, uncluttered single-purpose surface; oversized obvious targets; zero nested menus or window chrome. | Explicit verb-object labels (*"Approve Invoice"*, never *"OK"*); zero abbreviations; instant escape/close; automatic return to previous context. |
| **Daemonic** | Ongoing background processes (sync, imports, exports, AI generation, webhook monitors, scheduled jobs). | **No main screen.** Live quietly in a status indicator or job drawer. | Never interrupt sovereign work unless action is strictly required; when configuration is needed, open a *transient* settings sheet. |

**Rule of Blending:** Complex apps blend postures cleanly—e.g. a *Sovereign* Order Operations table that launches a *Transient* "Refund Order" drawer while a *Daemonic* CSV export runs in the background and notifies on completion.

---

## 2. Semantic IxD 4-Layer Architecture (Rosenberg — *UX Magic*)

Never jump from user stories to wireframes. Build the 4 layers in strict order:

### Layer 1: Grammar — The Object–Action–Attribute Matrix
Treat the app as a clean domain language (**Objects = Nouns**, **Actions = Verbs**, **Attributes = Adjectives**).

| Domain Object (Noun) | Universal Actions (Verbs) | Object-Specific Actions | Summary Attributes (List/Card) | Detail Attributes (Inspector) | Filter / Sort Attributes |
|---|---|---|---|---|---|
| *e.g. Order* | View, Search, Filter, Create, Edit, Archive, Export | Approve, Refund, Print Label | Order #, Customer, Total, Status, Date | Line items, Payment log, Audit trail | Status, Date range, Assignee |
| *e.g. Customer* | View, Search, Filter, Create, Edit, Archive, Export | Merge, Send Message | Name, Phone/Email, LTV, Status | Orders list, Notes, Addresses | Segment, Created date |

**Grammar Rules:**
1. **Minimize Object Count:** Consolidate overlapping DB tables into <= 7 user-facing conceptual objects (e.g., fold `order_items`, `order_notes`, `order_payments` into the `Order` object instead of 4 separate nav tabs).
2. **Enforce Verb Symmetry:** If `Filter`, `Archive`, `Export`, or `Duplicate` exist on `Orders` and `Customers`, they MUST live in the same position, use the same label/icon, and behave identically → **linear cognitive load** instead of exponential complexity.
3. **Name by User Mental Model:** Never expose engineering nouns (`TenantRecord`, `JobPayload`, `WebhookEventLog`) when users think `Workspace`, `Import`, `Delivery History`.

### Layer 2: Visualization — Semantic Grids & Widgets
Assign consistent spatial regions so users build **Spatial Memory** within minutes:
- **Left Rail / Top Nav:** Object Collections (Nouns).
- **Top Action Bar:** Collection-level Actions (Search, Filter, `+ New <Object>`).
- **Main Stage:** Object List/Grid/Canvas displaying *Summary Attributes*.
- **Right Slide-Over / Detail Pane:** Single Object *Detail Attributes* + contextual *Object-Specific Actions* (inherits object context—eliminates extra page loads!).
- **Elegance Discipline (Rosenberg Ch. 8):** Keep grids <= 3 primary columns; use a disciplined 3-tier typography hierarchy; limit semantic accent colors to 3 roles (Brand/Primary CTA, Semantic Status, Information Architecture).

### Layer 3: Flow — Shortest Context-Preserving Paths
- Actions are the transitions between states.
- **Inherit Context:** Triggering `Edit`, `Assign`, or `Approve` from a row or inspector keeps the user on the collection view (drawer/inline edit) instead of bouncing them across 3 separate pages and losing their scroll/filter position.

### Layer 4: Ethical Applied Game Theory (Optional — Only When Motivation Helps Users)
- Prefer **intrinsic motivators** (clear progress, mastery, autonomy, meaning) over manipulative extrinsic gimmicks.
- **Allowed:** Goal-Gradient progress bars during multi-step setup, clear completion streaks/checklists for onboarding, celebratory closure on milestone tasks.
- **Forbidden:** Dark patterns, artificial urgency timers, compulsive variable-reward traps (*User Friendly* + *Laws of UX*).

---

## 3. Simplification Moves (Colborne — *Simple and Usable*)

Apply in order whenever a screen, menu, or form feels heavy (designing for **Mainstreamers**, not vocal experts):

| Strategy | Operational Question | Concrete System-App Tactics |
|---|---|---|
| **1. Remove** | *Does 80% of mainstream users need this on every visit?* | Delete rarely-used columns, redundant fields, decorative cards, and half the instructional text (Krug's 3rd Law). Replace config flags with smart defaults. |
| **2. Organize** | *Are remaining items grouped with hard, non-overlapping edges?* | Chunk related items into groups of 3–5; align to tidy grids; order by frequency or workflow sequence; match user *desire paths*. Never use Search as a band-aid for broken browsing. |
| **3. Hide** | *Is it needed occasionally by experts or edge cases?* | Move secondary actions into `•••` overflow menus, collapsible "Advanced options" disclosures, or secondary tabs. Always leave a subtle discovery cue. |
| **4. Displace** | *Does this complexity belong on another surface or in the system itself?* | Keep mobile focused on quick triage/approvals and displace bulk editing/reporting to desktop; automate formatting, totals, and cleanup in code (Tesler's Law). |

---

## 4. Information Architecture — The 4 Systems (Rosenfeld, Morville & Arango)

Define all four explicitly for every system app:
1. **Organization System:** Primary navigation scheme (by **Domain Object** for ops/ERP apps, or by **Task/Workflow** for guided apps). Max hierarchy depth **<= 3 levels**.
2. **Labeling System:** One canonical **Controlled Vocabulary** table (1 term per concept—never call it "Client" in the sidebar, "Customer" in the table, and "Account" in the modal).
   - Navigation items = **Nouns** (*Orders, Customers, Reports*).
   - Action buttons = **Verb + Object** (*Create Order, Export CSV, Archive User*).
3. **Navigation System:** Global nav (persistent across app), Local nav (tabs/sub-sections within an object), Contextual links (cross-object jumps, e.g. Order → Customer), Breadcrumbs (always shown when depth >= 2). **Must pass Krug's Trunk Test on every deep route.**
4. **Search & Filter System:** Specify searchable fields, instant faceted filters for high-frequency attributes, clear active-filter chips with 1-click "Clear all", and helpful zero-result states.

---

## 5. Excise Eradication Playbook (Cooper — *About Face*)

Hunt down and kill all four categories of excise:
1. **Navigation Excise:** Eliminate forced full-page hops for quick inspection/editing → use **Two-Panel Master-Detail** or **List + Slide-Over Drawer**.
2. **Modal / Interruption Excise ("Stopping the Proceedings with Idiocy"):**
   - **Ban** "Saved successfully! [OK]" modals → use non-blocking 3–4s toast or inline saved badge.
   - **Ban** "Are you sure you want to archive?" modals for reversible actions → execute immediately + show **"Archived — [Undo]"** toast.
   - **Allow** blocking confirmation dialogs ONLY for irreversible, high-blast-radius actions (e.g., deleting a workspace, charging a card, sending bulk email to 10,000 users) — and state the exact impact (*"Delete 14 invoices permanently?"*).
3. **Form & Input Excise:** Pre-fill known data (user, org, currency, timezone); auto-format phone/dates/cards (Postel's Law); never clear valid fields when a submission fails.
4. **Welded-On Training Wheels:** Make onboarding checklists and tooltips dismissible once learned; never trap perpetual intermediates inside forced multi-screen wizards for daily tasks.

---

## 6. Inductive UI & Control Body Language (McKay — *UI is Communication*)

### Inductive UI Rules (Every Screen)
1. **Write the Human Conversation First:** Before designing a screen, write 2 sentences explaining the task as you would to a colleague sitting next to you.
2. **Explicit Main Instruction:** Every screen starts with a crisp header/sub-instruction answering *"What am I supposed to do here?"* (e.g., *"Review 12 pending payouts before Friday's batch"* — NOT *"Payouts Management"*).
3. **Single Purpose per Step:** Everything on the screen serves that instruction; remove or hide anything tangential.
4. **4-Question Element Audit (Run on every widget & text block):**
   - *Why is this element here?*
   - *What does it communicate?*
   - *Would an alternative control communicate better?*
   - *What would we lose if we removed it?*

### Control Selection & "Body Language" Guide

| Communication Need | Right Control | Body Language Warning |
|---|---|---|
| Single binary on/off setting (immediate effect) | **Toggle Switch** | Label must clearly describe the ON state; never require clicking "Save" after toggling unless grouped in a form. |
| Single opt-in / multi-select independent options | **Checkbox** | Label must make sense both checked and unchecked; avoid double negatives (*"Do not disable alerts"*). |
| Mutually exclusive choice (2–5 options) | **Radio Buttons / Segmented Control** | Keeps all options visible for instant recognition (prefer over dropdown when <= 5 options). |
| Mutually exclusive choice (6+ options) | **Select / Searchable Combobox** | Pre-selected default communicates *"leave this alone"*; placeholder *"Choose a category..."* communicates *"action required"*. |
| Primary immediate action (1 per view/section) | **Primary Filled Button** | Use Verb + Object (*"Publish Invoice"*); add ellipsis (`Export…`) if it opens a dialog first. |
| Secondary / cancel / navigation action | **Ghost/Secondary Button or Link** | Visually subordinate to Primary CTA (Von Restorff Effect); links navigate, buttons mutate state. |
| Multiple views of the **same** object | **Tabs** | **Never** use Tabs for sequential multi-step wizard flows (use a Stepper instead). |
| Approximate numeric value in a range | **Slider** | Must give instant visual preview; pair with numeric input if exact precision matters. |
| Structured text input | **Textbox sized to expected input** | Field width communicates expected length (short box for ZIP/CVV, wide box for address). |

---

## 7. System-App Pattern Catalog (Tidwell, Brewer & Valencia — *Designing Interfaces*, 3rd Ed.)

Match each system view to its proven structural archetype:

| Screen Job | Core Archetype | Recommended Patterns |
|---|---|---|
| **Monitor health & KPIs** | *Overview* | **Dashboard** with **Small Multiples**, **Data Spotlight**, **Datatips**, clear drilldown links to underlying lists. |
| **Triage / work through records** | *Focus + Do* | **Two-Panel Split View** or **Data Table + Slide-Over Inspector**, **Dynamic Queries** (live filters), **Bulk Action Bar**, **Inline Edit**, **List Inlay**. |
| **Create / configure complex object** | *Make* | **Single-Column Form** (<= 8 fields) or **Staged Wizard with Progress Indicator** (> 8 fields / branching logic), **Forgiving Format**, **Good Defaults & Smart Prefills**, **Preview** before submit. |
| **Visual / spatial / workflow editing** | *Make* | **Canvas + Palette**, **Movable/Collapsible Panels**, **Multilevel Undo**, **Keyboard-Only Shortcuts**. |
| **Mobile companion / field ops** | *Mobile* | **Bottom Navigation** (3–5 top-level destinations), **Vertical Stack**, **One-Window Drilldown**, **Cards**, **Touch Tools** (>= 44×44px targets), **Pull/Skeleton Loading**. |
| **System administration** | *Configure* | **Settings Editor** grouped into hard-edged categories with instant search, inline save or sticky "Unsaved changes" bar, **Escape Hatch** back to workspace. |

---

## 8. Form & Inclusive Design Standards (Wroblewski + Pickering)

### Form Design Checklist (*Web Form Design*)
- **Single-column layout** by default (clear vertical eye-tracking momentum; pair fields side-by-side ONLY when semantically one unit like First/Last Name or City/Postal).
- **Top-aligned labels** always visible (never placeholder-only labels that vanish on focus and break memory).
- **Mark the minority:** If most fields are required, mark optional ones `(optional)`; never clutter every label with `*` unless few are required.
- **Inline validation timing:** Validate *on blur* (or after first submit), and clear errors *live as the user fixes them* — never yell red while the user is still typing character 2 of an email.
- **Forgiving inputs (Postel's Law):** Accept spaces/dashes/parens in phone numbers, cards, and dates; normalize on the backend.
- **Primary button aligned with the left/start edge of inputs** (in RTL: right/start edge), visually distinct from Cancel/Reset (and almost never include a "Reset form" button—it's a slip trap!).

### Inclusive & RTL Engineering Baseline (*Inclusive Design Patterns*)
- **Native HTML first:** `<button>`, `<a href>`, `<label for>`, `<fieldset>/<legend>`, `<nav>`, `<main>`, `<dialog>` — never clickable `<div>`s.
- **Keyboard parity:** Every interactive action reachable via `Tab`/`Shift+Tab`, `Enter`/`Space`, `Escape` (closes modals/drawers and restores focus to trigger).
- **Focus management:** Visible high-contrast focus ring; trap focus inside open modals; announce async status changes via `aria-live="polite"` (or `"assertive"` for blocking errors).
- **Color independence:** Every status badge, chart series, and validation error pairs color with an icon and/or explicit text label (WCAG AA >= 4.5:1 text, >= 3:1 UI components).
- **Bilingual / Arabic RTL readiness:** Use CSS logical properties (`padding-inline`, `margin-inline-start`, `border-inline-end`, `text-align: start`), mirror directional icons (chevrons, back arrows), keep numbers/codes/emails explicitly `dir="ltr"` where appropriate.
