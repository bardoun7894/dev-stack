# 10-Point System-App UX Audit Rubric (Pre-Build & Pre-Ship)

Use this rubric in **Stage 7** (gate before build) and **Mode C** (auditing an existing system app). Rate every finding using the **Travis & Hodgson Severity Decision Tree** (`P0` Blocker, `P1` Serious, `P2` Medium, `P3` Low).

---

## 1. Outcome & Archetype Alignment (*Lean UX*, *Build Better Products*, *About Face*)
- [ ] Every screen ties to a concrete **user goal** (not a raw backend table or stakeholder feature dump).
- [ ] Designed for **perpetual intermediates / mainstreamers** — no welded-on beginner wizards blocking daily users, and no cryptic expert-only walls for newcomers.
- [ ] Application **Posture** (*Sovereign / Transient / Daemonic*) is explicit and consistent per surface.

## 2. Conceptual Model & Semantic Symmetry (*UX Magic*, *Design of Everyday Things*, *IA*)
- [ ] Domain objects are consolidated (`<= 7` top-level objects) — implementation/DB schema is hidden behind user vocabulary.
- [ ] **Controlled Vocabulary:** One canonical label per concept across nav, tables, drawers, modals, and errors.
- [ ] **Verb Symmetry:** Universal actions (`Search`, `Filter`, `Create`, `Edit`, `Archive`, `Export`) sit in the same place and behave identically across all objects.

## 3. Navigation & Krug's Trunk Test (*Don't Make Me Think*, *IA*)
- [ ] Hierarchy depth `<= 3` levels; breadcrumbs shown whenever depth `>= 2`.
- [ ] **Trunk Test passes on every deep route:** App ID, Page Name, Major Sections, Local Options, "You Are Here", and Search are all obvious within 3 seconds.
- [ ] Primary browsing works cleanly without relying on Search as a crutch.

## 4. Simplicity & Choice Budgets (*Simple and Usable*, *Paradox of Choice*, *Laws of UX*)
- [ ] Colborne's **Remove → Organize → Hide → Displace** applied: weak/rare options removed or hidden via progressive disclosure.
- [ ] Smart defaults pre-selected for 80% of users (satisficers); simultaneous visible choices capped at `3–4` where possible.
- [ ] Working memory chunks `<= 4–5` items; desktop layout `<= 3` primary visual columns.

## 5. Excise Eradication & Flow Efficiency (*About Face*, *Krug 2nd Law*, *Shneiderman*)
- [ ] Zero unnecessary page hops (uses Master-Detail, drawers, or inline edit inheriting object context).
- [ ] Zero "stopping the proceedings with idiocy" modals — reversible actions use **Undo** toasts instead of confirmation popups; blocking modals reserved strictly for irreversible high-impact actions.
- [ ] High-frequency daily actions are 1 click or keyboard shortcut away (Inflection).

## 6. Inductive Communication & Copy Discipline (*UI is Communication*, *Krug 3rd Law*, *Bright Ideas*)
- [ ] Every screen has a clear **Main Instruction** answering *"What am I supposed to do here?"* (zero vague "Manage" headers).
- [ ] Every element passes **McKay's 4-Question Audit** (Why is it here? What does it communicate? Better alternative? What's lost if removed?).
- [ ] Copy cut ruthlessly (Krug's 3rd Law) — zero "happy talk", jargon, or walls of instructional text.
- [ ] Controls match their **body language** (radio for 2–5 options, select for 6+, tabs only for views of the same object, single isolated primary CTA via Von Restorff).

## 7. Forms, Data Tables & Perceptual Ergonomics (*Web Form Design*, *Designing Interfaces*, *Mind in Mind*, *100 Things*)
- [ ] Forms are **single-column**, top-aligned labels (never placeholder-only), proportional widths, forgiving input formats (Postel's Law), inline validation on blur/fix.
- [ ] All **7 Gestalt principles** checked — zero accidental visual groupings.
- [ ] **Fitts's & Steering Laws:** Touch/click targets `>= 44×44px` mobile / `>= 36px` desktop, primary CTA near hand/eye focus, zero fragile cascading hover flyouts.
- [ ] Status & error alerts placed near **foveal focus** and never encoded by color alone.

## 8. Psychological Bottlenecks, Error Proofing & States (*Bottlenecks*, *Design of Everyday Things*, *Bright Ideas*)
- [ ] Core flow clears **Evans's Bottlenecks** (Attention → Perception → Memory/Signal-vs-Noise → Disposition → Motivation → Social).
- [ ] **Slips prevented** (destructive controls separated, no invisible modes, automated post-goal cleanup, autosave + Undo) and **Mistakes prevented** (live impact previews before destructive/bulk actions).
- [ ] Every error follows the **3-Part Contract** (*what happened*, *why*, *exact next fix*) in plain human language.
- [ ] All **5 UI States** defined per screen: *Empty, Loading, Populated, Partial/Filtered-Empty, Error* + deliberate **Peak–End** closure.

## 9. Responsiveness & Perceived Latency (*Mind in Mind*, *Laws of UX*)
- [ ] `<= 100 ms` click/toggle acknowledgement.
- [ ] `<= 400 ms` (Doherty Threshold) interactive transitions or optimistic UI.
- [ ] `400 ms – 1 s` skeleton/inline busy cue; `1 s – 10 s` determinate progress + Cancel; `> 10 s` async Daemonic background job.

## 10. Inclusion, Accessibility, RTL & Ethical Agency (*Inclusive Design Patterns*, *User Friendly*, *UX Magic*)
- [ ] Native semantic HTML, full keyboard navigation + visible focus + Escape-to-close, WCAG AA contrast (`>= 4.5:1` text / `>= 3:1` UI).
- [ ] Bilingual / Arabic **RTL** safe (CSS logical properties, mirrored directional icons, clean LTR isolation for codes/numbers).
- [ ] Ethical agency preserved — zero dark patterns, fake urgency, or manipulative loops.

---

## Audit Report Output Format (Mode C)

```markdown
# UX Audit Report — <App / Screen>
**Score:** <X / 100> | **Verdict:** Ship | Fix P0/P1 First | Redesign IA
**Findings Summary:** P0: <n> | P1: <n> | P2: <n> | P3: <n>

| ID | Sev | Location (Route / File:Line) | Broken Principle (Book) | What Users Experience | Concrete Fix |
|---|---|---|---|---|---|
| UX-01 | P0 | `/orders/:id` (`OrderView.tsx:84`) | Slip / Modal Excise (*About Face*, *Norman*) | Destructive Delete sits 4px next to Save with no Undo | Move Delete to overflow menu + add impact confirmation / soft-delete undo |
```
