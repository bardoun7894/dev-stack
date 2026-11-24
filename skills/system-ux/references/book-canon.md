# The UX Book Canon (30 Sources Mapped to System-App UX)

Complete deep-research synthesis of **all 23 books & ebooks** from the Interaction Design Foundation (IxDF) guide (`https://ixdf.org/literature/article/ux-design-books-guide`) plus **7 complementary UX specialty classics** essential for system applications.

---

## Part I — Core UX Foundations & Product Strategy (IxDF Books 1–11)

### 1. *UX for Beginners: A Crash Course in 100 Short Lessons* — Joel Marsh
- **Core Thesis:** Everything already has a UX; your job is to make it good by bridging human psychology, visual hierarchy, and measurable business goals.
- **Key Frameworks:** 100 modular lessons spanning user behavior, emotion framed as *gain vs. loss*, cognitive biases, IA, user flows, wireframing, and real-world metrics.
- **System-App Rule:** Great design lives inside users' heads, not the designer's. Tie every screen decision to both a user motivation and a business metric.
- **Pipeline Stage:** Stages 1, 2, 5.

### 2. *The Design of Everyday Things* (Revised Ed.) — Don Norman
- **Core Thesis:** "User error" is almost always a design failure. Human-Centered Design relies on **Discoverability** and **Understanding**.
- **Key Frameworks:**
  - **7 Fundamental Principles:** Discoverability, Feedback, Conceptual Model, Affordances, Signifiers, Mappings, Constraints (physical, cultural, semantic, logical).
  - **Two Gulfs:** Gulf of Execution (*"How do I do this?"*) and Gulf of Evaluation (*"What just happened?"*).
  - **7 Stages of Action:** Goal → Plan → Specify → Perform → Perceive → Interpret → Compare.
  - **3 Levels of Processing:** Visceral (reflex/first impression), Behavioral (expectation-driven skill/habit), Reflective (conscious reasoning/memory/trust).
  - **Error Taxonomy:** **Slips** (right goal, wrong execution: capture, description-similarity, mode-error, memory-lapse) vs. **Mistakes** (wrong goal/plan: rule-based, knowledge-based, memory-lapse).
- **System-App Rule:** Expose an accurate **System Image**; eliminate hidden modes; separate similar-looking destructive controls; provide immediate, continuous feedback and undo.
- **Pipeline Stage:** Stages 2, 5, 6.

### 3. *User Friendly: How the Hidden Rules of Design Are Changing the Way We Live, Work, and Play* — Cliff Kuang & Robert Fabricant
- **Core Thesis:** Hidden rules of design—metaphors, feedback loops, and error resilience—quietly mold human habits, trust, and society.
- **Key Frameworks:** Treating operator error as system failure (Three Mile Island lesson), the **Ladder of Metaphors**, visible feedback as the trust bridge, inclusive edge-case design driving mainstream breakthroughs, and the ethics of "frictionless" design (avoiding addictive feedback loops).
- **System-App Rule:** Design for human foibles and real environments rather than an idealized rational operator; widen human agency instead of manufacturing compulsive engagement.
- **Pipeline Stage:** Stages 2, 6.

### 4. *Don't Make Me Think (Revisited)* — Steve Krug
- **Core Thesis:** Users don't read—they **scan**, **satisfice** (pick the first good-enough option), and **muddle through**. Every screen must be self-evident.
- **Key Frameworks:**
  - **Krug's 3 Laws of Usability:** (1) Don't make me think! (2) Number of clicks doesn't matter if every click is a mindless, unambiguous choice. (3) Get rid of half the words on each page, then get rid of half of what's left.
  - **The Trunk Test:** From any deep internal screen, users must instantly see: Site ID, Page Name, Major Sections, Local Options, "You Are Here" indicator, and Search.
- **System-App Rule:** Kill "happy talk" and instructional paragraphs; make clickable targets unmistakable; pass the Trunk Test on every deep route.
- **Pipeline Stage:** Stages 3, 4, 5, 7.

### 5. *Rocket Surgery Made Easy* — Steve Krug
- **Core Thesis:** You don't need a lab to find the biggest UX problems—you only need to uncover as many serious problems as your team can actually fix.
- **Key Frameworks:** DIY qualitative usability testing cadence (**3 participants in one morning per sprint/month**, team observes live, debriefs over lunch); standardized **60-minute script** (Welcome 4m → Questions 2m → Home Tour 3m → Tasks 35m → Probing 5m → Wrap 5m); "Fix the most serious problems first" triage.
- **System-App Rule:** Test rough flows early with 3 users using neutral, realistic scenarios; resist adding new features to "fix" usability bugs—take things away first.
- **Pipeline Stage:** Stage 7.

### 6. *Lean UX: Applying Lean Principles to Improve User Experience* — Jeff Gothelf & Josh Seiden
- **Core Thesis:** Shift from shipping *outputs* (deliverables/features) to achieving *outcomes* (measurable changes in user behavior). Treat every requirement as an untested assumption.
- **Key Frameworks:** **8-Box Lean UX Canvas** (Business Problem → Business Outcomes → Users → User Outcomes → Solutions → Hypotheses → Riskiest Assumption → Least Work to Learn); **Hypothesis Statement** (*"We believe [outcome] will be achieved if [users] attain [benefit] with [feature]"*); Proto-Personas; Hypothesis Prioritization Canvas; Continuous Discovery + Dual-Track Agile.
- **System-App Rule:** Never design a screen without a falsifiable outcome hypothesis and an explicit riskiest assumption.
- **Pipeline Stage:** Stage 1.

### 7. *The Paradox of Choice: Why More Is Less* — Barry Schwartz
- **Core Thesis:** Excess choice triggers decision paralysis, anxiety, regret, and abandonment. People evaluate based on what is *easiest* to compare, not what is most important.
- **Key Frameworks:** **Satisficers** ("good enough") vs. **Maximizers** (exhaustive comparison → post-decision regret); smart defaults; recommended option highlighting; capping visible simultaneous options; progressive disclosure.
- **System-App Rule:** Pre-select the 80% default, highlight the recommended path, limit visible option sets to 3–4 comparable items where possible, and progressively disclose advanced settings.
- **Pipeline Stage:** Stages 3, 4, 5.

### 8. *UX Magic* — Daniel Rosenberg
- **Core Thesis:** Cognitive load can be predicted and minimized *before* wireframing by designing the application's linguistic interaction grammar—replacing "design Darwinism" (endless A/B guessing) with **Semantic Interaction Design (Semantic IxD)**.
- **Key Frameworks:**
  - **4 Sequential Layers:** (1) **Grammar** (Conceptual Model: Object–Action–Attribute Matrix with symmetrical verbs → *linear cognitive load*), (2) **Visualization** (Semantic Grids, specialized widgets, consistent Page Archetypes like Swimlane/Master-Detail/Calendar/Canvas), (3) **Flow** (actions as state transitions minimizing screen count and inheriting object context), (4) **Applied Game Theory** (Gamification, Gameful Interaction, Captology mapped to intrinsic/extrinsic motivators ethically).
  - **Elegance Rules (Ch. 8):** <= 3 grid columns, disciplined typography ("1-2-3 rule"), constrained 3-color semantic palette (brand, CTA, IA).
- **System-App Rule:** Build the Object–Action–Attribute Matrix *first*. Enforce verb symmetry across objects so learning one module teaches the entire system app.
- **Pipeline Stage:** Stages 3, 4, 5, 6.

### 9. *Build Better Products* — Laura Klein
- **Core Thesis:** A better product improves users' lives in a way that strengthens the business. Trying random things and abandoning them without study isn't iterating—it's flailing.
- **Key Frameworks:** **6-Stage Product Loop:** (1) Goal Setting (single measurable OKR + lifecycle friction + unit economics), (2) Empathy (provisional personas + qualitative interviews), (3) Creation (problem-tied ideation + behavior design), (4) Validation (surfacing & cheaply testing assumptions), (5) Measurement (built-in granular analytics + A/B), (6) Cross-functional Team Structure (avoiding both *silos* and *communes*).
- **System-App Rule:** Instrument behavioral analytics and funnel drop-off tracking at UX design time, not as a post-launch afterthought.
- **Pipeline Stage:** Stages 1, 7.

### 10. *Creative Confidence* — Tom Kelley & David Kelley
- **Core Thesis:** Creativity is a trainable muscle built through empathy, reframing everyday annoyances as design opportunities, and rapid low-stakes prototyping ("build to think").
- **Key Frameworks:** Guided mastery, "Observe like a traveler" (fresh eyes), balancing **Desirability** (human need) + **Feasibility** + **Viability**, bias toward rough prototypes while evidence can still change direction.
- **System-App Rule:** Prototype competing flow options cheaply before committing engineering sprints; treat early invalidation as a win.
- **Pipeline Stage:** Stages 1, 4, 7.

### 11. *100 Things Every Designer Needs to Know About People* — Susan M. Weinschenk, Ph.D.
- **Core Thesis:** Effective design aligns with empirical human perception, cognition, memory, emotion, social wiring, and unconscious decision-making.
- **Key Frameworks:** **10 Categories** — How People See (peripheral gist, faces, change blindness, 9% male colorblindness), Read (reading ≠ comprehension, screen fatigue), Remember (**~4 items working memory**, recognition > recall, reconstructive memory), Think (**Cognitive load > Visual load > Motor load**, progressive disclosure > click minimization, mental models), Focus Attention (selective attention, habituation, 7–10 min focus limit, multitasking myth), Motivate (Goal-Gradient effect, dopamine seeking, intrinsic mastery/autonomy), Social Animals (Dunbar's ~150, social etiquette online), Feel (aesthetics drive trust, stories > raw data), Make Mistakes (stress multiplies errors), Decide (unconscious processing, 3–4 item comparison cap).
- **System-App Rule:** Spend cheap *motor* clicks to save expensive *cognitive* effort; never rely on working memory > 4 items; show progress bars to trigger the Goal-Gradient effect.
- **Pipeline Stage:** Stages 4, 5, 6.

---

## Part II — UI Design, Cognitive Psychology & Interaction Patterns (IxDF Books 12–15)

### 12. *UI is Communication* — Everett N. McKay
- **Core Thesis:** A UI is an objective **human conversation** aimed at achieving user goals. If you can explain a task clearly in person, translate that exact conversation into the language of UI.
- **Key Frameworks:**
  - **10 Communication Principles:** UI is conversation; form follows communication; polite, respectful, forgiving tone; transcend mechanical usability.
  - **Conversation Patterns:** Speech, Monologue, App-Driven Dialogue (wizard), User-Driven Dialogue (progressive workspace).
  - **Inductive UI:** Break tasks into single-purpose steps; start every screen with an explicit **Main Instruction** answering *"What am I supposed to do here?"* (never vague headers like "Manage").
  - **Language of UI & Control Body Language:** Controls = words, commands = verbs, grouping = sentences, steps = paragraphs, errors/alerts = interruptions. Each control carries implicit body language (textbox width = expected length; pre-selected dropdown = don't change; tabs = views of the *same* object, not wizard steps).
  - **4-Question Element Audit:** Why is it here? What does it communicate? Would an alternative communicate better? What is lost if removed?
- **System-App Rule:** Write the human conversation and Main Instruction for every screen before placing controls; run the 4-Question Audit to prune noise.
- **Pipeline Stage:** Stages 4, 5.

### 13. *Designing with the Mind in Mind* (3rd Ed.) — Jeff Johnson
- **Core Thesis:** UI guidelines aren't arbitrary rules—they are direct consequences of human biological, perceptual, and cognitive architecture. Knowing *why* lets you make smart trade-offs.
- **Key Frameworks:**
  - **Perception:** Biased by past/present/future; limited color vision (edge contrast > hue); poor peripheral acuity (place feedback near foveal focus).
  - **7 Gestalt Principles:** Proximity, Similarity, Continuity, Closure, Symmetry, Figure/Ground, Common Fate.
  - **Reading & Memory:** Reading is unnatural; working memory is volatile; users follow *information scent* and **forget post-goal cleanup steps** (automate cleanup!).
  - **System 1 vs. System 2:** Learned habits are automatic; mental math and puzzle-solving kill flow.
  - **Hand–Eye Laws:** **Fitts's Law** (target size & distance) and **Steering Law** (avoid narrow cascading hover submenus).
  - **Engineering Time Constants:** `0.01s` visual fusion, **`0.1s`** cause-and-effect, **`1s`** uninterrupted train of thought, **`10s`** unit-task attention limit.
  - **Errors (3rd Ed.):** Slips vs. Mistakes; prevent, detect, recover.
- **System-App Rule:** Enforce hard latency tiers (`100ms / 1s / 10s`), automate post-completion cleanup, inspect every screen against all 7 Gestalt laws, and ban fragile hover corridors.
- **Pipeline Stage:** Stages 5, 6.

### 14. *Simple and Usable Web, Mobile, and Interaction Design* — Giles Colborne
- **Core Thesis:** Simplicity happens in the user's head—perceived clarity and control, not blind minimalism. Design for **Mainstreamers**, not vocal **Experts**.
- **Key Frameworks:** **4 Strategies for Simplicity:**
  1. **Remove** weak features, edge cases, unnecessary options, and verbose words; use smart defaults.
  2. **Organize** via chunking, hard-edged categories, visual grids, and user "desire paths" (never use Search as a crutch for bad browsing).
  3. **Hide** expert/infrequent controls behind progressive/staged disclosure with subtle discovery cues.
  4. **Displace** complexity to the right device/surface or to human judgment where appropriate (Conservation of Complexity).
- **System-App Rule:** Apply *Remove → Organize → Hide → Displace* to every cluttered screen, toolbar, and settings page.
- **Pipeline Stage:** Stages 3, 4, 5.

### 15. *Designing Interfaces* (3rd Ed.) — Jenifer Tidwell, Charles Brewer & Aynne Valencia
- **Core Thesis:** Recurring interaction problems have proven structural solutions (**patterns**) across desktop, web, and mobile—adapt patterns to context rather than inventing novel widgets.
- **Key Frameworks:** **12-Chapter Pattern Catalog:**
  - *People patterns:* Safe Exploration, Instant Gratification, Satisficing, Deferred Choices, Spatial/Prospective Memory, Streamlined Repetition, Keyboard Only.
  - *App Structure:* 4 screen archetypes (**Overview, Focus, Make, Do**); Dashboard, Canvas + Palette, Wizard, Settings Editor, Alternative Views, Many Workspaces.
  - *Navigation:* Hub-and-Spoke, Multilevel Tree, Step-by-Step, Pyramid, Flat; Breadcrumbs, Escape Hatch, Deep Links, Progress Indicator.
  - *Lists & Complex Data:* Two-Panel Selector / Split View, One-Window Drilldown, List Inlay, Cards, Pagination, Jump-to-Item; Datatips, Dynamic Queries, Data Brushing, Small Multiples.
  - *Actions & Forms:* Action Panel, Hover/Pop-up Tools, Prominent "Done", Preview, Cancelability, Multilevel Undo; Forgiving Format, Input Hints, Autocompletion, Good Defaults.
  - *Systems:* Atomic Design & component-based UI systems.
- **System-App Rule:** Map every system view to a canonical Tidwell archetype + list/action/form pattern so users benefit from instant familiarity (Jakob's Law).
- **Pipeline Stage:** Stages 4, 5.

---

---

> **Continued in [`book-canon-research-and-classics.md`](book-canon-research-and-classics.md):** Part III (UX Research & Psychological Constraints, Books 16–20), Part IV (Free Ebooks & *About Face*, Books 21–23), and Part V (7 Complementary UX Specialty Classics, Books 24–30).
