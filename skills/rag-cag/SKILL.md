---
name: rag-cag
description: Design and audit Hybrid RAG + CAG (Cache-Augmented Generation) and LLM KV/prompt caching across hosted APIs (Anthropic, OpenAI, Gemini, OpenRouter) and self-hosted GPU stacks (vLLM + LMCache + CacheBlend). Splits knowledge into a byte-identical Cold/CAG prefix and a dynamic Hot/RAG suffix, removes prefix cache-busters (timestamps, per-user state, reordered docs), wires explicit cache_control breakpoints, and tracks cached_tokens hit rates. Triggers on "rag vs cag", "cag", "cache-augmented generation", "hybrid rag", "prompt caching", "kv cache", "lmcache", "cacheblend", "cut llm input cost", "speed up ai replies", and Arabic/Darija "كاش البرومبت", "تخزين الكاش للـ AI", "RAG ولا CAG".
---

# rag-cag — Hybrid RAG + CAG & KV Prompt Caching

Standard RAG hits a vector DB or recomputes the entire system prompt on every turn — even for static rules, tool schemas, policies, and business facts that haven't changed in weeks. Agentic workloads re-send ~60%+ repeated input tokens every step.

**Hybrid RAG + CAG** fixes this by splitting context into two layers:
- **Cold / Static layer (CAG — cached in KV memory):** system instructions, tool schemas, policies, business profile, canonical reference docs. Placed at **byte 0** in a **fixed, deterministic order**.
- **Hot / Dynamic layer (RAG — fetched per query):** live DB rows, user/lead state, retrieved chunks, timestamps (`now()`), one-shot notes, recent conversation turns. Always placed **after** the Cold boundary.

## Files

| Path | What |
|---|---|
| `references/providers.md` | Wire formats (`cache_control`, automatic prefix caching, cached token usage fields), Laravel/TS/Python recipes, and LMCache + CacheBlend guide |
| `scripts/audit_prompt_cache.py PATH [--json]` | Read-only scan for prefix cache-busters (`PC01`–`PC04`); exit 1 on high findings |
| `tests/test_audit_prompt_cache.py` | Regression tests for the auditor |

Run the auditor with `python3 ~/.claude/skills/rag-cag/scripts/audit_prompt_cache.py <path>` (stdlib only, Python 3.10+).

## Decision Matrix: CAG vs RAG vs Hybrid

| Knowledge type | Changes | Size | Layer | Mechanism |
|---|---|---|---|---|
| System prompt, persona, guardrails, tool schemas | Rarely (days/weeks) | 2K–50K tokens | **Cold (CAG)** | Exact static prefix + `cache_control: {"type": "ephemeral"}` |
| Business profile, offers, SOPs, canonical FAQs | Rarely | Fits easily in prefix | **Cold (CAG)** | Exact static prefix (byte-identical across all users) |
| Live user/contact/lead state, current timestamp, handback notes | Every turn / per user | Small | **Hot (dynamic)** | Placed **after** Cold boundary |
| Large / frequently updated corpus, per-query lessons, ticket history | Often or > context budget | Large | **Hot (RAG)** | Retrieve top-K per query; place **after** Cold boundary |
| Multi-document RAG on self-hosted GPUs (varying doc order/combos) | Mixed | Large | **Self-hosted KV** | **LMCache** (disaggregated KV store) + **CacheBlend** (order-independent doc reuse) |

Rule of thumb: **never cache everything** (you blow the context window and pay storage/prefill overhead), and **never RAG static policies** (you pay latency and retrieval error on every query).

## The 5 Iron Rules

1. **Cold first, Hot last.** Every byte of static instructions, skills, tool definitions, and reference digests goes at the very start of the prompt. Dynamic context (per-user records, retrieved RAG chunks, `now()` clock, handback notes) goes strictly after the Cold boundary.
2. **Byte-identical order.** Prefix caching matches byte-for-byte from token 0. Sort skill/doc filenames alphabetically, sort tool schemas deterministically, and keep JSON key order stable. Reordering two cached docs turns both into misses.
3. **Zero volatile data in the Cold prefix.** Never interpolate `now()`, `Date.now()`, `datetime.now()`, request IDs, contact names, or lead stages inside the Cold layer. One changed character at byte 500 invalidates 20,000 tokens after it.
4. **Wire provider caching cleanly.**
   - **Anthropic / Claude proxy / OpenRouter (Claude & Gemini):** split the system message into multipart text blocks with `cache_control: {"type": "ephemeral"}` on the Cold block (only when Cold length meets the provider's minimum cacheable threshold, typically >= 1,024 tokens / ~3,500–4,000 chars, or >= 1,024 chars configurable).
   - **OpenAI / Gemini direct / DeepSeek:** automatic prefix caching — just keeping Cold first and byte-identical unlocks hits automatically.
   - **Single-prompt bridges (e.g. `agy`):** still keep Cold strictly before Hot so any upstream prefix cache hits and prompt layout stays clean.
   - **Self-hosted GPU (`vLLM`, `SGLang`, `TensorRT-LLM`):** when prefix caching stalls because RAG reorders/combines separately cached documents or in-process KV I/O slows inference, run **LMCache** (separate process sharing GPU memory across GPU/CPU/SSD/remote tiers) with **CacheBlend** (selectively recomputes cross-document attention tokens for 2–4x faster multi-doc RAG).
5. **Measure hit rates and lock with a test.**
   - Extract cached input tokens from every response (`usage.prompt_tokens_details.cached_tokens` on OpenAI/OpenRouter/Gemini, `usage.cache_read_input_tokens` + `usage.cache_creation_input_tokens` on Anthropic) and apply cached pricing in cost estimates.
   - Add a regression test asserting that two requests for **different users at different timestamps** produce a **100% byte-identical Cold prefix**.

## Audit & Refactor Workflow

1. **Audit first:** run `audit_prompt_cache.py` on the app's AI/prompt services to find `PC01`–`PC04` issues.
2. **Check precedence invariants:** before moving any block, check tests for security/precedence rules (e.g. an owner-facts block that must appear after retrieved RAG lessons so owner facts override stale lessons — keep that block in the Hot layer right after lessons while moving all other static blocks into Cold).
3. **Split Cold vs Hot:** introduce a small helper (e.g. `PromptCache::systemMessage($cold, $hot)`) that preserves plain-string `$message['content']` compatibility for tests while carrying the exact Cold prefix byte boundary for the HTTP LLM client.
4. **Emit `cache_control` at the wire boundary:** in the HTTP client (`OpenAiChatLlm` / TS / Python wrapper), strip internal metadata and convert the Cold/Hot split into multipart blocks with `cache_control` when the provider supports it and the Cold prefix meets the minimum length.
5. **Track cached tokens & test:** record cached tokens in usage/cost tracking, write byte-identity + `cache_control` + usage tests, and run the full test suite.
