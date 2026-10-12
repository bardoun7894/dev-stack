---
name: webmcp
description: Expose a website's user flows as agent-callable tools with Chrome WebMCP (document.modelContext). Use when adding or building any web page, form, checkout, search, booking or user flow on a website; when the user says "WebMCP", "agent-ready site", "expose tools to AI agents"; Arabic "WebMCP", "أدوات للوكلاء". Covers Next.js, Laravel/Blade, declarative forms, and testing.
---

# WebMCP: tools for web flows

WebMCP lets a page register tools that in-browser agents can call, instead of scraping the DOM. Add it as a progressive enhancement on public user flows.

## When to add

- Public flows: search, browse, filter, add-to-cart, booking, contact forms, status lookups.
- NOT admin or destructive actions, unless the tool sets `consequentialHint: true` and the page asks the user to confirm.
- Skip pages with no meaningful user action (static content).

## Rules

1. Feature-detect `document.modelContext` (it is on `document`, not `navigator`). Do nothing when absent.
2. Progressive enhancement: the page must work identically without WebMCP.
3. No third-party polyfill in production.
4. Tools call existing same-origin routes or server actions and reuse the user's session. Never add a new privileged endpoint for agents.
5. `inputSchema` is JSON Schema; the server still validates every input as usual. Treat tool input as untrusted.
6. Names are clear `verb_noun` (`search_products`, `add_to_cart`). Descriptions say what it does and what it returns.
7. Annotate: `readOnlyHint` for reads, `consequentialHint` for purchases/deletes/sends, `untrustedContentHint` when results contain user-generated content.
8. Unregister on unmount/navigation by aborting the `AbortController` passed as `{signal}` to `registerTool`.
9. Pass tool input as an object (JSON-stringified args are deprecated from Chrome 155).
10. `registerTool` returns a promise (Chrome 156) that rejects with AbortError on unregister: always `.catch` it and ignore it when the signal is aborted.

## Imperative API

```js
const ac = new AbortController();
document.modelContext?.registerTool({
  name: 'search_products',
  description: 'Search the catalog by text. Returns matching products.',
  inputSchema: { type: 'object', properties: { q: { type: 'string' } }, required: ['q'] },
  annotations: { readOnlyHint: true },
  execute: async ({ q }, { signal }) => {
    const r = await fetch(`/api/products?q=${encodeURIComponent(q)}`, { signal });
    return { content: [{ type: 'text', text: await r.text() }] };
  },
}, { signal: ac.signal });
// cleanup: ac.abort()
```

## Next.js recipe

Copy `assets/nextjs/WebMcpTools.tsx`, define the typed tool list for the page, mount `<WebMcpTools tools={tools} />` in the page or layout. It is a client component; it registers in `useEffect` and aborts on cleanup. Fetch existing route handlers or call server actions from `execute`.

## Laravel / Blade recipe

Copy `assets/blade/webmcp.blade.php` to `resources/views/partials/`, then in the page: `@push('scripts') @include('partials.webmcp', ['tools' => [...]]) @endpush`. POST fetches send the CSRF token header. Tools hit existing web routes so session, policies and validation apply.

## Declarative form recipe

```html
<form action="/contact" method="post" toolname="send_contact"
      tooldescription="Send a message to the site owner" >
  <input name="email" type="email" toolparamdescription="Sender email" required>
  <textarea name="message" toolparamdescription="Message body"></textarea>
  <button>Send</button>
</form>
```

Add `toolautosubmit` only for non-consequential forms. In the submit handler: `e.preventDefault(); if (e.agentInvoked) e.respondWith(promise)`. Style agent activity with `:tool-form-active` and `:tool-submit-active`. Listen for `toolactivated` / `toolcancel` on `document.modelContext` (window.ontool* is unsupported from Chrome 156).

## Testing recipe

1. Unit: `assets/test/modelContext.mock.ts` fakes `document.modelContext.registerTool`, records tools and honors abort. `assets/test/WebMcpTools.test.tsx` shows asserting register on mount, unregister on unmount, and no-op when unsupported.
2. Live: Chrome with `chrome://flags/#enable-webmcp-testing` enabled; open the page and inspect registered tools in DevTools (AI assistance), then call a tool and check the network request.
3. Headless/server (verified on Chrome for Testing 156.0.8078.4, Linux): without a flag `document.modelContext` is undefined; with `--enable-features=WebMCPTesting` (or `--enable-experimental-web-platform-features`) it is an object and `registerTool` succeeds. `navigator.modelContext` stays undefined. Serve the page from `http://127.0.0.1` or https; data: URLs were not tested.
   ```ts
   const browser = await chromium.launch({ args: ['--enable-features=WebMCPTesting'] });
   const page = await browser.newPage();
   await page.goto('http://127.0.0.1:3000/checkout');
   expect(await page.evaluate(() => typeof document.modelContext)).toBe('object');
   ```
   Then assert the tools registered, through a test hook the app exposes or through the CDP `WebMCP` domain (experimental; verified on Chrome 156.0.8078.4):
   - `WebMCP.enable` / `WebMCP.disable`. Events: `toolsAdded`, `toolsRemoved`, `toolInvoked`, `toolResponded`.
   - `WebMCP.invokeTool {frameId, toolName, input: <object>}` returns `{invocationId}`. Cancel with `WebMCP.cancelInvocation {invocationId}`. The result arrives as `toolResponded {invocationId, status, output, errorText, exception}`; `status` was `Completed`.
   - Over CDP, annotations arrive as `readOnly`, `consequential`, `untrustedContent`, `debugging` booleans.
   - A declarative form completes without a user submit only with `toolautosubmit`. Without it, the response waits for a submit.
   - Wait for navigation to commit before evaluating. The target is listed before the page script runs.
   CLI smoke check (page sets `document.body.dataset.mc = typeof document.modelContext`; run as root needs `--no-sandbox`): `chrome --headless=new --no-sandbox --enable-features=WebMCPTesting --dump-dom http://127.0.0.1:8000/index.html | grep -o 'data-mc="[^"]*"'` prints `data-mc="object"`.
4. Reusable e2e harness: `skills/webmcp/references/e2e-2026-10-12/e2e.mjs` (Node 22+, no deps). Run from that folder: `CHROME=/path/to/chrome node e2e.mjs`. Env: `CHROME` (default is a Linux Playwright path), `OUT` (default: script dir, receives `after.png`), `DEMO_DIR` (default `./demo`), `ONLY_NEGATIVE=1` (flag-off control only). It starts `python3 -m http.server` on a free 127.0.0.1 port, launches headless Chrome with `--headless=new --no-sandbox --remote-debugging-port=<free>` (flag on, then off), drives the tools over CDP, prints a PASS/FAIL table and exits 1 on any failure. Profiles go to `/tmp/webmcp-e2e-prof-*`. `webmcp-domain.json` is the protocol description. Known issue: the last row of `run.txt` (run B) fails with `Cannot set properties of null` at `#q` (querySelector returned null; cause not diagnosed). `run-negative.txt` is the clean control.

## Scope notes

- Tools are same-origin. Cross-origin iframes need `allow="tools"`; `exposedTo` limits listed origins.
- `debugging` annotation needs Chrome 156+. Unregistering keeps in-flight runs (Chrome 153+).

## Status (verified 2026-10-12; re-check if older than 90 days)

Chrome origin trial (register a token, `<meta http-equiv="origin-trial">`) or the local testing flag. Chrome only. Spec is a W3C Community Group draft. Known consumers: Chrome/Gemini agent ("soon") and DevTools AI assistance; no evidence Claude clients call it yet, so treat it as forward-looking.

Sources: https://developer.chrome.com/docs/ai/webmcp , /imperative-api , /declarative-api , /secure-tools ; spec https://webmachinelearning.github.io/webmcp/ ; demos https://github.com/GoogleChromeLabs/webmcp-tools ; notes in `references/research-2026-10-12.md`.
