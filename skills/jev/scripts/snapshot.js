// Atomic page observation for jev-browse. ONE evaluate returns visible text, the indexed action table,
// a per-node guard and a page marker — instead of a separate round trip per element list, aria snapshot
// and validity sweep.
//
// Node identity lives in a WeakMap on `window`, so an id survives a framework re-render and a node that
// vanished is DETECTED rather than silently re-matched by array index. Nothing is written to the DOM under
// test (the old `data-jev` attribute polluted the page and was wiped by React).
//
// Ported from browser-use/jev-ultrafast (MIT), with two deliberate changes:
//  1. Lightpanda parses the DOM but never lays it out: rects are 0x0, `elementFromPoint` and
//     `checkVisibility` are missing. Every geometric test is therefore gated on `hasLayout`; without it
//     the agent falls back to DOM-only visibility and offers no scrolling, instead of filtering the whole
//     page away and reporting `stuck`.
//  2. Password fields ARE observed (login flows are the main use case and get their value from --data),
//     but their value never leaves the browser: the guard and the page key carry the length, never the
//     secret, and the text helper is not allowed to write into them.
(() => {
  if (!document.body) return null;
  const cache = (window.__jevBrowse = window.__jevBrowse || { ids: new WeakMap(), nodes: new Map(), next: 1 });
  const nodeId = (e) => {
    if (!cache.ids.has(e)) cache.ids.set(e, cache.next++);
    const n = cache.ids.get(e);
    cache.nodes.set(n, e);
    return n;
  };
  for (const [n, e] of cache.nodes) if (!e.isConnected) cache.nodes.delete(n);

  let hasLayout = false;
  try {
    hasLayout = typeof document.elementFromPoint === 'function' && window.innerWidth > 0
      && document.body.getBoundingClientRect().height > 0;
  } catch { hasLayout = false; }
  cache.hasLayout = hasLayout;

  const ROLES = ['button', 'link', 'checkbox', 'radio', 'switch', 'tab', 'menuitem', 'menuitemradio',
    'option', 'gridcell', 'combobox', 'textbox', 'searchbox', 'spinbutton'];
  const SELECTOR = 'a[href],button,input,textarea,select,summary,[contenteditable="true"],'
    + ROLES.map((r) => `[role="${r}"]`).join(',');
  const attr = (e, k) => (e.getAttribute ? e.getAttribute(k) : null);
  const matches = (e, s) => { try { return e.matches(s); } catch { return false; } };

  const roleOf = (e) => {
    const explicit = attr(e, 'role');
    if (ROLES.includes(explicit)) return explicit;
    if (e.tagName === 'BUTTON' || e.tagName === 'SUMMARY') return 'button';
    if (e.tagName === 'A') return 'link';
    if (e.tagName === 'SELECT') return 'combobox';
    if (e.tagName === 'TEXTAREA' || e.isContentEditable) return 'textbox';
    if (e.tagName === 'INPUT') {
      if (['checkbox', 'radio'].includes(e.type)) return e.type;
      if (['button', 'submit', 'reset', 'image'].includes(e.type)) return 'button';
      if (e.type === 'search') return 'searchbox';
      if (e.type === 'number') return 'spinbutton';
      // Date/time inputs open a picker on click and are typed into; without them here a form containing one
      // is simply invisible to the agent.
      if (['text', 'email', 'url', 'tel', 'password', 'date', 'datetime-local', 'month', 'week', 'time']
        .includes(e.type)) return 'textbox';
    }
    return null;
  };

  // Accessible name, near enough: aria-labelledby -> aria-label -> <label> -> value -> alt -> text -> title
  // -> placeholder. Replaces the old ad-hoc label(), which missed aria-labelledby and label wrapping.
  const name = (e, seen) => {
    seen = seen || new Set();
    if (!e || seen.has(e)) return '';
    seen.add(e);
    const ref = (attr(e, 'aria-labelledby') || '').split(/\s+/).filter(Boolean)
      .map((x) => name(document.getElementById(x), seen)).filter(Boolean).join(' ');
    const own = e.tagName === 'INPUT' ? '' : [...e.childNodes].map((n) => (
      n.nodeType === 3 ? n.textContent
        : n.nodeType === 1 && attr(n, 'aria-hidden') !== 'true' ? name(n, seen) : '')).join(' ');
    return String(ref
      || attr(e, 'aria-label')
      || [...(e.labels || [])].map((l) => name(l, seen)).filter(Boolean).join(' ')
      || (['button', 'submit', 'reset'].includes(e.type) ? e.value : '')
      || attr(e, 'alt') || own || attr(e, 'title') || attr(e, 'placeholder') || ''
    ).trim().replace(/\s+/g, ' ').slice(0, 80);
  };

  const hiddenByDom = (e) => !!(e.closest && e.closest('[aria-hidden="true"],[inert],[hidden]'));
  const visible = (e) => {
    if (hiddenByDom(e)) return false;
    if (!hasLayout) return true;
    if (typeof e.checkVisibility === 'function'
      && !e.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) return false;
    const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const centre = (e) => {
    const r = e.getBoundingClientRect();
    return { x: r.x + r.width / 2, y: r.y + r.height / 2, w: r.width, h: r.height };
  };
  const onScreen = (e) => {
    if (!hasLayout) return true;
    const c = centre(e);
    return c.w > 0 && c.h > 0 && c.x >= 0 && c.y >= 0 && c.x < innerWidth && c.y < innerHeight;
  };
  const disabled = (e) => matches(e, ':disabled') || !!(e.closest && e.closest('[aria-disabled="true"]'));
  const host = (h) => String(h || '').replace(/^www\./, '');
  const isExternal = (e) => {
    try {
      const u = new URL(attr(e, 'href'), location.href);
      return !['http:', 'https:'].includes(u.protocol) || host(u.hostname) !== host(location.hostname);
    } catch { return true; }
  };
  // A password value never leaves the browser; its length is enough to tell "filled" from "empty".
  const shown = (e) => (e.type === 'password' ? (e.value ? `••• (${e.value.length})` : '') : String(e.value ?? ''));

  // Re-checked immediately before every input. Meaning and identity, never geometry: geometry is resolved
  // and hit-tested at execution time, so an animation alone does not invalidate a decision.
  // Identity and meaning of the ELEMENT only. Upstream also hashed the surrounding container's text, which
  // works on a static page and makes a live app untestable: a dashboard with a clock, a counter or a sync
  // badge rewrites that text between the decision and the click, so every target reads as "changed" and
  // nothing can ever execute (EDUNEX: stop=stale, 0 steps). What actually protects a click is this identity
  // plus the viewport and occlusion checks execute.js runs immediately before input.
  cache.guard = (e) => {
    if (!e || !e.isConnected || !visible(e)) return null;
    return [cache.ids.get(e), roleOf(e), name(e), shown(e), e.checked ?? null, e.selectedIndex ?? null,
      e.readOnly ?? null, disabled(e), attr(e, 'aria-expanded'), attr(e, 'aria-checked'),
      attr(e, 'aria-selected'), attr(e, 'href')];
  };
  cache.pageKey = () => [location.href, hasLayout ? [scrollX, scrollY, innerWidth, innerHeight] : 0,
    [...document.querySelectorAll('input,textarea,select')]
      .filter((e) => !['file', 'hidden'].includes(e.type))
      .map((e) => [nodeId(e), shown(e), e.checked, e.selectedIndex, e.disabled, e.readOnly])];

  const actions = [];
  for (const e of document.querySelectorAll(SELECTOR)) {
    if (['file', 'hidden'].includes(e.type)) continue;
    if (!visible(e) || disabled(e) || !onScreen(e)) continue;
    const role = roleOf(e);
    if (!role) continue;
    if (role === 'gridcell' && e.querySelector('button,[role="button"]')) continue;
    const node = nodeId(e);
    const base = { node, role, label: name(e) || role };
    for (const k of ['checked', 'selected', 'expanded']) {
      const v = attr(e, 'aria-' + k);
      if (v !== null) base[k] = v;
    }
    if (['checkbox', 'radio'].includes(e.type)) base.checked = String(e.checked);
    if (e.tagName === 'A') { base.href = attr(e, 'href'); base.external = isExternal(e); }
    if (e.tagName === 'SELECT') {
      const current = [...e.selectedOptions].map((o) => o.label).join(', ');
      const options = [...e.options]
        .filter((o) => !o.selected && !o.disabled && !(o.closest && o.closest('optgroup[disabled]')))
        .map((o) => ({ value: o.value, label: o.label }));
      if (options.length) actions.push({ ...base, kind: 'select', value: current, options });
      continue;
    }
    const editable = !e.readOnly && attr(e, 'aria-readonly') !== 'true'
      && (['textbox', 'searchbox', 'spinbutton'].includes(role)
        || (role === 'combobox' && ['INPUT', 'TEXTAREA'].includes(e.tagName)));
    const value = 'value' in e ? shown(e)
      : (e.isContentEditable || role === 'combobox') ? String(e.innerText || '').trim() : '';
    if (editable) {
      actions.push({ ...base, kind: 'fill', type: e.type || e.tagName.toLowerCase(), value,
        empty: !value, secret: e.type === 'password' });
      // Only a field that actually opens something gets a second, clickable entry: an autocomplete listbox
      // or a date picker. Offering "Open …" for every plain text input just padded the CLICK head.
      const opens = role === 'combobox' || attr(e, 'aria-autocomplete') || attr(e, 'aria-controls')
        || attr(e, 'aria-owns') || ['date', 'datetime-local', 'month', 'week', 'time'].includes(e.type);
      if (opens) actions.push({ ...base, kind: 'click', value, label: 'Open ' + base.label });
    } else {
      actions.push({ ...base, kind: 'click', value,
        inForm: !!(e.closest && e.closest('form')) && role === 'button' });
    }
  }

  // Visible text only. An offscreen footer or article body used to fill the budget with text the agent
  // cannot act on. Without layout there is nothing to intersect, so take the document.
  let text = '';
  if (hasLayout && typeof document.createTreeWalker === 'function') {
    const words = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const range = document.createRange();
    let n, len = 0;
    while ((n = walker.nextNode()) && len < 6000) {
      const v = n.textContent.trim(), parent = n.parentElement;
      if (!v || !parent || parent.closest('script,style,noscript,template') || !visible(parent)) continue;
      range.selectNodeContents(n);
      const r = range.getBoundingClientRect();
      if (r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth) {
        words.push(v); len += v.length;
      }
    }
    text = words.join('\n');
  } else {
    text = String(document.body.innerText || document.body.textContent || '');
  }
  text = text.slice(0, 6000);

  // Native constraint validation (type=email, required) blocks submit with a tooltip that is not in the DOM.
  const nativeValidation = [...document.querySelectorAll('input,select,textarea')]
    .filter((e) => e.validity && !e.validity.valid && e.validationMessage)
    .map((e) => `${name(e) || e.name || e.id || e.type}: ${e.validationMessage}`).slice(0, 10);

  const scrollHeight = document.documentElement.scrollHeight || 0;
  const omitted = Math.max(0, actions.length - 250);
  actions.splice(250);
  actions.forEach((a, i) => { a.index = String(i + 1); });
  if (hasLayout && scrollY + innerHeight < scrollHeight - 2) actions.push({ kind: 'scroll', id: 'SCROLL_DOWN', label: 'Scroll down', delta: 560 });
  if (hasLayout && scrollY > 0) actions.push({ kind: 'scroll', id: 'SCROLL_UP', label: 'Scroll up', delta: -560 });

  const guards = {};
  for (const a of actions) if (a.node != null && !(a.node in guards)) guards[a.node] = cache.guard(cache.nodes.get(a.node));
  // Compare meaning and identity only — see cache.guard.
  const semantics = actions.map(({ node, ...rest }) => rest);
  const marker = JSON.stringify([location.href, document.title, text, semantics,
    hasLayout ? [scrollX, scrollY] : 0]);

  return { url: location.href, title: document.title, hasLayout, text, nativeValidation,
    scroll: { y: hasLayout ? scrollY : 0, height: scrollHeight, viewport: hasLayout ? innerHeight : 0 },
    actions, guards, marker, pageKey: JSON.stringify(cache.pageKey()), omitted };
})()
