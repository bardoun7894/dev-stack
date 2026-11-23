# Provider Prompt Caching & Self-Hosted KV Cache Reference

## 1. Hosted API Matrix

| Provider / Route | Caching mode | Minimum cacheable prefix | Wire format | Usage fields to read |
|---|---|---|---|---|
| **Anthropic (Messages API & Claude via OpenRouter)** | Explicit breakpoints | 1,024 tokens (Sonnet/Opus), 2,048–4,096 (Haiku) | `{"type": "text", "text": cold, "cache_control": {"type": "ephemeral"}}` | `cache_read_input_tokens`, `cache_creation_input_tokens` (OpenRouter also maps `prompt_tokens_details.cached_tokens`) |
| **OpenRouter (Gemini & Claude models)** | Explicit `cache_control` on OpenAI-compat `messages[].content` array | 1,024–2,048 tokens | `content: [{type: "text", text: cold, cache_control: {type: "ephemeral"}}, {type: "text", text: hot}]` | `usage.prompt_tokens_details.cached_tokens` (and `usage.cost` already reflects discount) |
| **OpenAI (GPT-4.1 / GPT-5 / o-series)** | Automatic prefix caching | 1,024 tokens (128-token increments) | Plain string or blocks — exact byte prefix at index 0 | `usage.prompt_tokens_details.cached_tokens` |
| **Google Gemini API** | Implicit prefix caching + Explicit Context Caching API | 1,024–2,048 tokens (implicit); 32K+ (explicit TTL cache) | Keep static prefix at start of `systemInstruction` / contents | `usageMetadata.cachedContentTokenCount` |
| **DeepSeek / Qwen APIs** | Automatic prefix caching | 64–1,024 tokens | Exact byte prefix at index 0 | `prompt_cache_hit_tokens` / `prompt_tokens_details.cached_tokens` |

### Cached Read Pricing Rule of Thumb
- Cached input reads typically cost **10% of normal input price** (90% discount on Anthropic / Gemini; 50–75% discount on OpenAI).
- Cache writes (when explicit, e.g. Anthropic 5-min TTL) cost ~1.25x normal input once, then break even after 2 reads within the TTL window.

---

## 2. Clean Code Patterns

### Pattern A: Non-breaking Cold/Hot Helper (Laravel / PHP)

Keep `content` as a single string for tests and simple bridges (`agy`), while tagging the exact byte offset where the Cold CAG prefix ends so the HTTP client can emit `cache_control` blocks on the wire:

```php
final class PromptCache
{
    public const PREFIX_BYTES_KEY = '_cache_prefix_bytes'; // secret-scan:allow

    /** @return array{role: string, content: string, _cache_prefix_bytes?: int} */
    public static function systemMessage(string $cold, string $hot = ''): array
    {
        $cold = rtrim($cold);
        $hot = ltrim($hot);
        $content = $hot === '' ? $cold : $cold."\n\n".$hot;

        $message = ['role' => 'system', 'content' => $content];
        if ($cold !== '') {
            $message[self::PREFIX_BYTES_KEY] = strlen($cold);
        }

        return $message;
    }
}
```

At the HTTP boundary (`OpenAiChatLlm::prepareMessages()`):
1. Strip `_cache_prefix_bytes` before sending JSON.
2. If the provider supports explicit `cache_control` AND the Cold prefix length is >= the minimum cacheable byte threshold (e.g. `>= 1024` bytes, ~250–350 tokens — or `>= 3072` bytes for strict 1024-token parity):
   - Split `$content` into `$cold = substr($content, 0, $prefixBytes)` and `$hot = ltrim(substr($content, $prefixBytes))`.
   - Send:
     ```json
     {
       "role": "system",
       "content": [
         {"type": "text", "text": "<cold>", "cache_control": {"type": "ephemeral"}},
         {"type": "text", "text": "<hot>"}
       ]
     }
     ```
3. Otherwise send the plain string `content` unchanged.

### Pattern B: TypeScript / Next.js (OpenAI / OpenRouter / Anthropic SDK)

```ts
export function buildSystemMessage(cold: string, hot: string, explicitCache: boolean) {
  const cleanCold = cold.trimEnd();
  const cleanHot = hot.trimStart();

  if (!explicitCache || cleanCold.length < 3072) {
    return { role: 'system' as const, content: cleanHot ? `${cleanCold}\n\n${cleanHot}` : cleanCold };
  }

  return {
    role: 'system' as const,
    content: [
      { type: 'text' as const, text: cleanCold, cache_control: { type: 'ephemeral' as const } },
      ...(cleanHot ? [{ type: 'text' as const, text: cleanHot }] : []),
    ],
  };
}
```

### Pattern C: Extracting Cached Tokens (Provider-Agnostic)

```php
$cached = (int) (
    $usage['prompt_tokens_details']['cached_tokens']
    ?? $usage['cache_read_input_tokens']
    ?? $usage['prompt_cache_hit_tokens']
    ?? 0
);
```

---

## 3. When Prefix Caching Stops Working: LMCache + CacheBlend (Self-Hosted GPU Only)

Prefix caching has two hard ceilings:
1. **Rigid prefix matching:** If you cache Doc A alone and Doc B alone, then a RAG query retrieves `[Doc A, Doc B]` (or `[Doc B, Doc A]`), Doc B's prefix no longer matches → cache miss.
2. **In-process I/O contention:** Running KV cache compression/offload inside the inference engine stalls GPU compute while tensors move between GPU, CPU RAM, and SSD.

### Architecture when self-hosting `vLLM` / `SGLang` / `TensorRT-LLM`
- **Repo:** https://github.com/LMCache/LMCache
- **Disaggregated cache process:** LMCache runs alongside the inference engine and exchanges tiny block-ID messages over shared GPU memory while handling GPU/CPU/SSD/remote parallel loading in its own process (fault-tolerant: engine degrades gracefully to uncached if LMCache restarts; cache survives engine crash).
- **CacheBlend:** Exploits attention locality — only a small fraction of tokens attend across document boundaries. CacheBlend selectively recomputes those tokens and reuses the rest of each independently cached document, yielding 2–4x faster multi-doc RAG regardless of document order.
- **Do NOT deploy LMCache for hosted APIs** (Anthropic, OpenAI, OpenRouter, Gemini, `agy`) or CPU-only VPS hosts — you do not control the inference engine's KV tensors there. Use Hybrid RAG + CAG + prefix caching instead.
