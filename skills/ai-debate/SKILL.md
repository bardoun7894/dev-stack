---
name: ai-debate
description: Multi-Agent Debate technique between Gemini, Grok, and Claude. Gemini acts as Systems Architect (proposing the design), Grok acts as Devil's Advocate (hunting fatal assumptions, edge cases, and failure modes), and Claude acts as Maestro / Independent Synthesizer (weighing trade-offs, adjudicating claims, and authoring a bulletproof final decision). Includes an automated Stage 4 Storyteller that crafts a full dramatic War-Room story of the debate. Use whenever facing complex architectural decisions, high-risk technical tradeoffs, contentious implementation paths, or when asked to "run a debate", "make AI debate itself", "gemini vs grok vs claude", or "/ai-debate".
allowed-tools: Bash, Read, Write, Grep, Glob
---

# Multi-Agent Debate (Gemini vs Grok vs Claude + War-Room Story)

An automated 4-stage peer adversarial debate technique based on MIT and Google Multi-Agent Debate research. Rather than relying on a single model's blind spots or affirmative bias, distinct frontier models debate the problem:

1. **Stage 0: Grounded Research (`Perplexity / Sonar-Pro`)**: Real-time prior art, benchmarks, and external standards.
2. **Stage 1: Architect (`Gemini`)**: Formulates the engineering proposal, explores alternatives (`O1`, `O2`, `O3`), technical stack, and initial design.
3. **Stage 2: Devil's Advocate (`Grok` with quota fallback to `Claude Red-Team`)**: Attacks the proposal, hunts hidden operational costs, single points of failure, edge cases, second-order effects, and naive assumptions.
4. **Stage 3: Maestro / Synthesizer (`Claude`)**: Adjudicates the debate objectively, filters out hyperbole, cross-examines evidence, builds a definitive criteria comparison table, and delivers a battle-tested decision and execution plan.
5. **Stage 4: Storyteller (`War-Room Narrative`)**: Synthesizes the human and technical drama into a full, cinematic story detailing the clash, the tension, the intellectual breakthrough, and the final consensus.

---

## When to Use

- High-stakes architectural choices (e.g. storage engine, auth model, multi-tenancy, IPC/event-bus).
- Difficult trade-offs where every option has severe downsides.
- Stress-testing a plan before committing weeks of development.
- Generating a rich, compelling narrative explanation/story of a technical decision for team alignment or content creation.
- User requests: "make them debate", "make a story about the debate", "run a debate between models", "gemini vs grok vs claude", "تجادل النماذج", "/ai-debate".

---

## Architecture & Execution

Run the verified pipeline script located at:
```bash
# On MyContabo (Server-First)
ssh MyContabo '/usr/local/bin/ai-debate "<Topic or Question>" -o /root/transcribe/data/media/debate_<slug>.md'

# Or locally
python3 ~/.claude/skills/ai-debate/scripts/ai_debate.py "<Topic or Question>" -o ./debate_output.md
```
To skip story generation: add `--skip-story`.
