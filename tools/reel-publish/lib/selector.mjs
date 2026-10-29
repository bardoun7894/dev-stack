// Selector support for BridgePage. A selector is comma-separated alternatives; the union is returned in document order.
// Forms: `text=Foo`, `css:has-text("Foo")`, plain CSS.

// Split on commas that are not inside quotes, [], () or {}.
export function splitSelector(selector) {
  const out = [];
  let depth = 0;
  let quote = null;
  let cur = '';
  for (let i = 0; i < selector.length; i++) {
    const c = selector[i];
    if (quote) {
      cur += c;
      if (c === '\\' && i + 1 < selector.length) cur += selector[++i];
      else if (c === quote) quote = null;
      continue;
    }
    if (c === '"' || c === "'" || c === '`') { quote = c; cur += c; continue; }
    if (c === '[' || c === '(' || c === '{') depth++;
    else if ((c === ']' || c === ')' || c === '}') && depth > 0) depth--;
    if (c === ',' && depth === 0) { out.push(cur.trim()); cur = ''; continue; }
    cur += c;
  }
  out.push(cur.trim());
  return out.filter(Boolean);
}

// Runs inside the page (stringified into Runtime.evaluate). Pure DOM, no closures over Node scope.
// mode: 'el' -> element | null, 'elvis' -> element only if visible, 'state' -> {exists, visible} | null, 'count' -> number
function engine(alts, index, hasText, mode) {
  const norm = (s) => String(s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const textOf = (el) => norm(el.innerText !== undefined ? el.innerText : el.textContent);
  const visible = (el) => {
    const b = el.getBoundingClientRect();
    if (!(b.width > 0 && b.height > 0)) return false;
    const view = el.ownerDocument.defaultView || window;
    const v = view.getComputedStyle(el).visibility;
    return v !== 'hidden' && v !== 'collapse';
  };
  const docs = [];
  (function walk(d) {
    docs.push(d);
    for (const f of d.querySelectorAll('iframe,frame')) {
      try { if (f.contentDocument) walk(f.contentDocument); } catch (e) { /* cross-origin */ }
    }
  })(document);

  const all = [];
  for (const d of docs) {
    const found = new Set();
    for (const alt of alts) {
      if (alt.startsWith('text=')) {
        let raw = alt.slice(5).trim();
        const q = raw[0];
        if ((q === '"' || q === "'") && raw.endsWith(q) && raw.length > 1) raw = raw.slice(1, -1);
        const needle = norm(raw);
        const hits = [];
        for (const el of d.querySelectorAll('body *')) {
          const tag = el.tagName;
          if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT') continue;
          if (!visible(el)) continue;
          if (textOf(el).includes(needle)) hits.push(el);
        }
        for (const el of hits) if (!hits.some((o) => o !== el && el.contains(o))) found.add(el);
      } else {
        const texts = [];
        const css = alt.replace(/:has-text\(\s*(["'])((?:\\.|(?!\1).)*)\1\s*\)/g, (_m, _q, t) => { texts.push(norm(t)); return ''; }).trim();
        for (const el of d.querySelectorAll(css || '*')) {
          if (texts.every((t) => textOf(el).includes(t))) found.add(el);
        }
      }
    }
    all.push(...[...found].sort((a, b) => (a === b ? 0 : (a.compareDocumentPosition(b) & 4) ? -1 : 1)));
  }
  const filtered = hasText ? all.filter((el) => textOf(el).includes(norm(hasText))) : all;
  if (mode === 'count') return filtered.length;
  const el = index < 0 ? filtered[filtered.length + index] : filtered[index];
  if (!el) return null;
  if (mode === 'state') return { exists: true, visible: visible(el) };
  if (mode === 'elvis') return visible(el) ? el : null;
  return el;
}

export const ENGINE_SOURCE = engine.toString();

// Expression for Runtime.evaluate.
export function engineExpression(alts, index, hasText, mode) {
  return `(${ENGINE_SOURCE})(${JSON.stringify(alts)}, ${index}, ${JSON.stringify(hasText || null)}, ${JSON.stringify(mode)})`;
}
