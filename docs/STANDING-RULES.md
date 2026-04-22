# Dev-stack standing rules — codex + gemini + panel

These rules apply every time the `codex`, `gemini`, or `panel` skill fires on this stack. They are committed to the repo so teammates inherit them automatically via `team-mode`. Per-user memory (`~/.claude/projects/<project>/memory/`) mirrors them for individual sessions.

---

## 1. Role split for critical tasks

On critical / load-bearing tasks, route work by each reviewer's strongest axis. Claude's context is the scarce resource — offload heavy thinking to the CLIs; keep Claude for synthesis + execution + user-facing decisions.

| Reviewer | Strongest at | Use for |
|---|---|---|
| **Gemini** (`gemini -p`) | plan + design | long-context plans, multi-module spec+code, design critique, UI/frontend, design-system drift |
| **Codex** (`codex exec`, gpt-5.4) | plan + review | focused code review, bug hunt, security, narrow implementation plan |
| **Claude** (this session) | research + synthesis + execution | `/kb-query` + NotebookLM, reconciling CLI outputs, final artifact, handing to specialist subagents |
| **Panel** (all three) | triangulation | architecture decisions, pre-merge on high-risk diffs, multi-module load-bearing plans |

**Priority ordering:**
1. Claude context / token preservation.
2. Artifact quality (panel > single CLI > Claude alone, for load-bearing work).
3. Speed — last. Never sacrifice 1 or 2 for 3 on critical work.

**Skip delegation on:** trivial single-file fixes, interactive debugging, synthesis-only tasks where Claude already has the context loaded.

---

## 2. Token-save priority (mandatory)

CLI outputs persist to `ai-knowledge-base/raw/{codex,gemini,panel}/` FIRST. Claude reads the artifact by file reference when synthesizing — never hold multi-page CLI responses in Claude's live context when a file path will do.

Applied across every skill in this triad:
- `codex` skill → `raw/codex/<YYYY-MM-DD>-<slug>.md`
- `gemini` skill → `raw/gemini/<YYYY-MM-DD>-<slug>.md`
- `panel` skill → `raw/panel/<YYYY-MM-DD>-<slug>.md` (full 3-round transcript)

All three get promoted to `knowledge/` by `/kb-ingest`.

---

## 3. Frontend work routes to gemini

Any frontend / UI / React / Next.js / Tailwind / CSS / design-adjacent request → invoke the `gemini` skill as part of the flow:

- **Plan phase**: `gemini -p --approval-mode plan` for multi-module UI plans before `writing-plans`.
- **Review phase**: after frontend-engineer writes code, run gemini design-review (screenshots + component code + `DESIGN.md`) before declaring done.

**Accessibility guard:** `which gemini` check first. If the CLI is not accessible, fall back silently to normal frontend flow (`frontend-engineer` + `frontend-design` / `polish` / `audit`). Never gate the whole task on gemini — log and continue if it errors.

**Critical frontend → escalate to `/panel`** so codex adds the focused-review axis alongside gemini's design axis.

---

## 4. KB + SSH awareness for the CLIs

Codex and Gemini get the same research footing as Claude — KB always in scope, off-host data staged by Claude before the CLI runs.

### KB always in scope

Every invocation includes `~/ai-knowledge-base/` in the CLI workspace so they can read `knowledge/`, `raw/`, `daily/`, `reports/` directly — not just the Prior-art block Claude injects.

```bash
# codex
CODEX_WORKSPACE="$PROJECT_ROOT:$HOME/ai-knowledge-base" codex exec \
  --sandbox read-only \
  "<prompt>" 2>&1

# gemini
gemini -p "<prompt>" \
  --approval-mode plan \
  --include-directories "$PROJECT_ROOT,$HOME/ai-knowledge-base" \
  -o text 2>&1
```

### Off-host data via SSH — Claude stages, CLIs read

If the target file / log / DB dump lives on a remote host configured in `~/.ssh/config` (Contabo, Hostinger, etc.) and not in the current folder, Claude runs the fetch FIRST, stages the data into a temp dir, then points the CLI at the local copy.

```bash
STAGE=$(mktemp -d)
rsync -a user@host:/path/to/remote/data "$STAGE/"

# then:
codex exec --sandbox read-only "<prompt referencing $STAGE>" 2>&1
# or:
gemini -p "<prompt referencing $STAGE>" \
  --approval-mode plan \
  --include-directories "$PROJECT_ROOT,$HOME/ai-knowledge-base,$STAGE" \
  -o text 2>&1
```

### Mid-run "I need data from X"

If codex or gemini reports missing data mid-review, stop, let Claude fetch via SSH, stage it, re-run the CLI with the staged dir added to the workspace. Never hand the CLIs raw network credentials — Claude owns the network side, they stay in `--sandbox read-only` / `--approval-mode plan`.

---

## 5. Panel inherits everything above

When `/panel` fires:
- Research (`/kb-query` + NotebookLM) runs **once** — all three reviewers share the Prior-art block (no parallel KB storms).
- KB paths + any SSH-staged dirs are added to the workspace **once** before Round 1.
- Round 1 (independent drafts) + Round 2 (cross-review) reuse the same workspace.
- Round 3 (Claude synthesis) writes the full transcript with consensus + majority + preserved minority dissent + unresolved conflicts for user tiebreak.
- Panel splits 1/1/1 → stop, surface to user, do NOT pick a winner.

---

## 6. Never-cross-the-line guardrails

- Codex `--sandbox read-only`; Gemini `--approval-mode plan`. Never upgrade without explicit user request.
- Neither CLI writes code on this stack. They propose — Claude + specialist subagents (`frontend-engineer`, `backend-engineer`, `designer`) execute.
- `gemini --yolo` is FORBIDDEN in these skills.
- No raw network credentials into CLI prompts. SSH fetches happen outside the CLI boundary.
- Panel never auto-fires inside `/kb-dev`. Explicit invocation or explicit "this is load-bearing" only.

---

## Sources

These rules originated from:
- `~/.claude/projects/-Users-mohamedbardouni/memory/feedback_frontend_gemini.md`
- `~/.claude/projects/-Users-mohamedbardouni/memory/feedback_critical_task_routing.md`
- `~/.claude/projects/-Users-mohamedbardouni/memory/feedback_cli_kb_ssh_awareness.md`

Individual session memory mirrors them locally. This file is the team-wide source of truth committed to the dev-stack repo.
