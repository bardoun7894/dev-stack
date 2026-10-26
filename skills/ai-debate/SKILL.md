---
name: ai-debate
description: Multi-Agent Debate technique between Gemini, Grok, and Claude. Gemini acts as Systems Architect (proposing the design), Grok acts as Devil's Advocate (hunting fatal assumptions, edge cases, and failure modes), and Claude acts as Maestro / Independent Synthesizer (weighing trade-offs, adjudicating claims, and authoring a bulletproof final decision). Use whenever facing complex architectural decisions, high-risk technical tradeoffs, contentious implementation paths, or when asked to "run a debate", "make AI debate itself", "gemini vs grok vs claude", or "/ai-debate".
allowed-tools: Bash, Read, Write, Grep, Glob
---

# Multi-Agent Debate (Gemini vs Grok vs Claude)

An automated 3-stage peer adversarial debate technique based on MIT and Google Multi-Agent Debate research. Rather than relying on a single model's blind spots or affirmative bias, three distinct frontier models debate the problem:

1. **Architect (Gemini)**: Formulates the engineering proposal, explores alternatives (`O1`, `O2`, `O3`), technical stack, and initial design.
2. **Devil's Advocate (Grok)**: Attacks the proposal, hunts hidden operational costs, single points of failure, edge cases, second-order effects, and naive assumptions.
3. **Maestro / Synthesizer (Claude)**: Adjudicates the debate objectively, filters out hyperbole, cross-examines evidence, builds a definitive criteria comparison table, and delivers a battle-tested decision and execution plan.

---

## When to Use

- High-stakes architectural choices (e.g. storage engine, auth model, multi-tenancy, IPC/event-bus).
- Difficult trade-offs where every option has severe downsides (e.g. native root vs external hardware vs acoustic processing).
- Stress-testing a plan before committing weeks of development.
- Breaking out of single-model echo chambers or sycophancy.
- User requests: "make them debate", "run a debate between models", "gemini vs grok vs claude", "تجادل النماذج", "/ai-debate".

---

## Architecture & Execution

The debate can be executed either directly via the CLI runner or manually step-by-step through orchestration.

### 1. Automated CLI Runner
Run the verified pipeline script located at:
```bash
# On MyContabo (Server-First)
ssh MyContabo '/usr/local/bin/ai-debate "<Topic or Question>" -o /root/transcribe/data/media/debate_<slug>.md'

# Or locally
python3 ~/.claude/skills/ai-debate/scripts/ai_debate.py "<Topic or Question>" -o ./debate_output.md
```

### 2. Manual Orchestration Protocol

When executing within an agent session across harnesses (Claude Code, Antigravity `agy`, or OpenAI `codex`):

#### Phase 1: Gemini (Architect)
- **Role**: Systems Architect.
- **Instruction**: Propose a concrete architecture with explicit option codes (`O1`, `O2`, `O3`). Define the technical stack, runtime hooks, latency/quality trade-offs, and failure boundaries.
- **Command**:
  ```bash
  agy -p "أنت المهندس المعماري للنظم. الموضوع المطلوب: <Topic>..."
  ```

#### Phase 2: Grok (Devil's Advocate)
- **Role**: Ruthless auditor and red-team reviewer.
- **Instruction**: Given Gemini's proposal, hunt every hidden cost, single point of failure (SPOF), platform constraint, and real-world failure mode. Rate vulnerabilities from P0 to P2.
- **Command**:
  ```bash
  grok --model grok-4.7-build-fast --effort low --prompt-file <path_to_gemini_output> --output-format plain --always-approve
  ```

#### Phase 3: Claude (Maestro & Synthesizer)
- **Role**: Chief Architect & Neutral Arbiter.
- **Instruction**: Evaluate both perspectives. Identify where Gemini was naive, where Grok was overly cynical, assemble a criteria comparison matrix, and specify the definitive verdict for enterprise and individual use cases.
- **Command**:
  ```bash
  claude -p "<Neutral prompt with Gemini and Grok summaries>" < /dev/null
  ```

---

## Output Standards

Every debate artifact must adhere to:
1. **Clear Option Codes**: `O1`, `O2`, `O3` maintained across all three models.
2. **Comparison Matrix**: Evaluation across Quality, Compatibility, Security/Compliance, Maintenance overhead, and Field Reliability.
3. **Dual Execution Paths**:
   - Enterprise/Commercial path (compliance, centralized control, liability).
   - Personal/Power-user path (cost, autonomy, performance).
4. **Actionable Punch List**: Numbered decisions (`D1`, `D2`, `D3`) and risks (`R1`, `R2`).
