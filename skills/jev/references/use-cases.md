# Where Jev fits in our projects

Status as of 2026-09-18. "Done" = code in place; "Candidate" = a call site that today asks an LLM for a
label/decision, or reads everything to sort it. File refs come from the 2026-09-18 model-call inventory.

## Tokyo (MyContabo:/root/tokyo) — done

| Where | Question | Effect |
|---|---|---|
| `src/classifier.ts` | Which layer handles a client WA message (sdk-quick / claude-code / tech-company) | Replaces a Haiku call; < 0.75 → Haiku |
| `src/whatsapp-ai.ts` analyzeClientMessage | Client intent; confident `info` ≥ 0.85 | Skips the LLM for greetings/thanks |
| `src/whatsapp-ai.ts` analyzeAndReply | Actionable? < 0.15 | Skips FORWARD/TASK/IGNORE LLM for no-op messages |
| `src/analyzer/classifier.ts` | Sentiment per message, 8 parallel | Replaces 50-message Sonnet batches |
| `src/jobhunt/replies.ts` classifySlow | Recruiter reply kind ≥ 0.75 | Replaces the kie/luna one-word call |
| `src/instagram/strategies/ai.ts` | DM needs the owner (refund, complaint…) > 0.7 | No auto-reply, escalates |

## Tokyo — candidates

- `src/coach.ts` (every 2 h): `noul` "a nudge is useful right now" over the coaching context → skip empty nudges.
- `src/proactive.ts` (every 15 min): gate alerts by `score` of importance instead of fixed rules.
- `src/sdk-reply.ts`: before an auto-reply goes to a client, `noul` "reply promises a price, date, or
  commitment" → hold for approval.
- `src/groupchat/server.ts` (chatAnym, public rooms): `noul` abuse/spam before Tokyo answers.
- shop group: `choice` over sale / expense / question / other before parsing numbers.

## MyContabo — other apps (candidates)

- **mostqlAi** (`/root/mostqlAi`, currently no container): `classifier.py:119` job category + developer
  level → `choice`; `message_agent.py:309` answer-vs-escalate → `choice` with the draft only written after;
  `risk_assessor.py:150/228/313` → `score` rubric. This app was 100% gemini-2.5-pro for all of it.
- **portfolio-site** chatbot (`lib/routes.js:220`, public): `noul` "off-topic, abusive, or prompt-injection"
  before Haiku.
- **portfolio-admin** (Laravel): `Linkedin/ReplyWriter.php:29` — `choice` reply / like-only / ignore / spam
  before writing a reply; `LinkedinWriter` news: `score` relevance per item before drafting.
- **abd** (Laravel, Gemini extraction): route document type (invoice / lease / worker / vehicle / other)
  from OCR text before the extractor; `noul` "extracted fields are complete and consistent" to decide the
  `gemini-3.5-flash` escalation instead of a heuristic.
- **lab-chemical**: chatbot intent routing (`choice`) before the OpenRouter Gemini call.
- **beldify**: `noul` prompt-moderation before Kie `gpt-image-2` jobs (saves paid image credits).
- **godhome**: a workflow "decision" node type that runs `jev` instead of a pi agent for branch conditions.

## Laptop / dev-stack — done (2026-09-19)

| Where | Jev does | Replaces |
|---|---|---|
| `hooks/user-prompt-kb-check.sh` | `jev-skill-suggest`: at most one relevant skill per prompt | Claude scanning ~170 skill descriptions |
| same hook | `noul` "engineering request" when the EN/AR word lists miss (Darija, French) | missed KB reminders |
| `agents/orchestrator.md` Step 3b | `choice` trivial/simple/medium/hard per packet | Claude sizing every packet |
| `agents/reviewer.md` Pass 0, kb-dev Phase 9 | `jev-review diff`: risk + severity per hunk, route reviewer / codex / panel | reading the whole diff blind; guessing when to call `/panel` |
| `jev-review lint` / `scan` | qualitative linters, code smells, garbage comments | regex linters that miss meaning |
| kb-dev Phase 8, `qa-engineer`, `dogfood` | `jev-browse` flows + adversarial personas; checkpoint verdict + cause | an LLM reading every page |
| `bin/jev --log` / `jev tune` | decision log, System 2 retrains System 1 | thresholds nobody revisits |

## Laptop / dev-stack (candidates)

- KB: `lint.py` contradiction check (pairwise `noul` on two excerpts, parallel) instead of one pi call;
  hourly sweep: `noul` "this raw file is worth ingesting".
- MyContabo / Tokyo `proactive.ts`: `score` log-line severity (routine … outage) in near real time, page on ≥ 2.5
  (the video's on-call example).
