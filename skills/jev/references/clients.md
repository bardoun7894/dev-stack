# Jev clients

All three return `null`/`None` when the key is missing, the call fails, or confidence is below the bar —
the caller always keeps its existing path as the fallback. Env: `OPENROUTER_API_KEY`, optional `JEV_MODEL`.

## Wire format

```http
POST https://openrouter.ai/api/alpha/decisions
Authorization: Bearer $OPENROUTER_API_KEY
Content-Type: application/json

{"model":"typesafe/jev-1.13",
 "state": "text" | {…} | […],
 "questions": {
   "intent":  {"type":"choice","instructions":"…","criteria":{"bug":"…","question":"…","other":"…"}},
   "urgent":  {"type":"noul","instructions":"…"},
   "anger":   {"type":"score","instructions":"…","criteria":["calm","annoyed","furious"]}}}
```
```json
{"model":"typesafe/jev-1.13-20260917",
 "answers":{"intent":{"type":"choice","choice":"bug","probabilities":{"bug":1,"question":0,"other":0},"confidence":1},
            "urgent":{"type":"noul","noul":0.88},
            "anger":{"type":"score","score":1.4,"confidence":0.8}},
 "usage":{"input_tokens":372,"output_tokens":57,"cost":0.0000156}}
```

## TypeScript / Node (Tokyo, godhome, Next.js route handlers)

Reference implementation: `MyContabo:/root/tokyo/src/jev.ts` (`askJev`, `jevChoice`, `jevNoul`, tests in
`src/jev.test.ts`). Minimal copy:

```ts
const URL = process.env.JEV_DECISIONS_URL || "https://openrouter.ai/api/alpha/decisions";
const MODEL = process.env.JEV_MODEL || "typesafe/jev-1.13";

export async function askJev(state: unknown, questions: Record<string, unknown>, timeoutMs = 3000) {
  const key = process.env.OPENROUTER_API_KEY;
  if (!key) throw new Error("jev_no_key");
  const r = await fetch(URL, {
    method: "POST",
    headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
    body: JSON.stringify({ model: MODEL, state, questions }),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!r.ok) throw new Error(`jev_${r.status}`);
  return (await r.json()).answers as Record<string, any>;
}

export async function jevChoice<T extends string>(
  state: unknown, instructions: string, criteria: Record<T, string>, min = 0.8,
): Promise<T | null> {
  try {
    const a = (await askJev(state, { q: { type: "choice", instructions, criteria } })).q;
    return a?.choice in criteria && (a.confidence ?? 0) >= min ? a.choice : null;
  } catch { return null; }
}
```

## PHP / Laravel (portfolio-admin, abd, beldify, …)

`config/services.php`: `'openrouter' => ['key' => env('OPENROUTER_API_KEY'), 'jev_model' => env('JEV_MODEL', 'typesafe/jev-1.13')],`

```php
<?php

namespace App\Services;

use Illuminate\Support\Facades\Http;

class Jev
{
    /** Raw call: returns the answers map, or null on no key / error. */
    public static function ask(array|string $state, array $questions, int $timeout = 5): ?array
    {
        $key = config('services.openrouter.key');
        if (! $key) {
            return null;
        }
        try {
            $r = Http::withToken($key)->timeout($timeout)->post('https://openrouter.ai/api/alpha/decisions', [
                'model' => config('services.openrouter.jev_model', 'typesafe/jev-1.13'),
                'state' => $state,
                'questions' => $questions,
            ]);
            return $r->successful() ? $r->json('answers') : null;
        } catch (\Throwable $e) {
            report($e);
            return null;
        }
    }

    public static function choice(array|string $state, string $instructions, array $criteria, float $min = 0.8): ?string
    {
        $a = self::ask($state, ['q' => ['type' => 'choice', 'instructions' => $instructions, 'criteria' => $criteria]])['q'] ?? null;
        return ($a && array_key_exists($a['choice'] ?? '', $criteria) && ($a['confidence'] ?? 0) >= $min) ? $a['choice'] : null;
    }

    public static function noul(array|string $state, string $instructions): ?float
    {
        return self::ask($state, ['q' => ['type' => 'noul', 'instructions' => $instructions]])['q']['noul'] ?? null;
    }
}
```
Queue it (`dispatch(fn () => …)`) when it runs over many rows; the cost is negligible, the latency isn't.

## Python (mostqlAi, KB scripts, FastAPI services)

```python
import json, os, urllib.request

def ask_jev(state, questions, timeout=10):
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return None
    req = urllib.request.Request(
        os.environ.get("JEV_DECISIONS_URL", "https://openrouter.ai/api/alpha/decisions"),
        data=json.dumps({"model": os.environ.get("JEV_MODEL", "typesafe/jev-1.13"),
                         "state": state, "questions": questions}).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "User-Agent": "jev-client/1.0"},  # default urllib UA gets Cloudflare 1010
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r).get("answers")
    except Exception:
        return None

def jev_choice(state, instructions, criteria, min_conf=0.8):
    a = (ask_jev(state, {"q": {"type": "choice", "instructions": instructions, "criteria": criteria}}) or {}).get("q")
    return a["choice"] if a and a.get("choice") in criteria and a.get("confidence", 0) >= min_conf else None
```
TypeSafe also ships `typesafe_sdk` (Python) with `Choice` / `Noul` / `Score` models — it targets
`api.typesafe.ai` (waitlist) and cannot be pointed at OpenRouter by `base_url`; use the client above.
