// Guarded execution for jev-browse. Called as EXECUTE + '(' + JSON.stringify(req) + ')' so the arguments
// are embedded literals, never a selector, coordinate or snippet produced by a model.
//
// req = { node, kind, value?, text?, delta?, guard, pageKey?, realInput? }
// Returns null when the decision no longer refers to this page (node gone, renamed, disabled, moved
// offscreen, or covered by an overlay) — the driver then re-observes instead of clicking the wrong thing.
// Returns { point:{x,y} } when the driver asked for real input and the target validated.
// Returns { done:true } when the action was performed in the DOM.
((req) => {
  const cache = window.__jevBrowse;
  if (!cache) return null;
  const hasLayout = !!cache.hasLayout;

  if (req.kind === 'scroll') {
    window.scrollBy(0, req.delta);
    return { done: true };
  }
  if (req.kind === 'wait') return { done: true };

  const e = cache.nodes.get(req.node);
  if (!e || !e.isConnected) return null;
  // Identity and meaning must still match what was observed when the decision was made.
  if (JSON.stringify(cache.guard(e)) !== JSON.stringify(req.guard)) return null;
  // Only checked when nothing was typed this step: every fill changes the page key by design.
  if (req.pageKey != null && JSON.stringify(cache.pageKey()) !== req.pageKey) return null;
  if (req.kind === 'fill' && (e.readOnly || e.getAttribute('aria-readonly') === 'true')) return null;

  let point = null;
  if (hasLayout) {
    const r = e.getBoundingClientRect();
    const x = r.x + r.width / 2, y = r.y + r.height / 2;
    if (!r.width || !r.height || x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) return null;
    // An element under a cookie banner or modal backdrop reports a fine rect and clicks the overlay.
    const top = document.elementFromPoint(x, y);
    if (top && !e.contains(top) && !top.contains(e)) return null;
    point = { x, y };
  }

  if (req.kind === 'select') {
    if (e.tagName !== 'SELECT') return null;
    const ok = [...e.options].some((o) => o.value === req.value && !o.disabled
      && !(o.closest && o.closest('optgroup[disabled]')));
    if (!ok) return null;
    e.value = req.value;
    e.dispatchEvent(new Event('input', { bubbles: true }));
    e.dispatchEvent(new Event('change', { bubbles: true }));
    return { done: true };
  }

  // A submit control whose form posts to another origin would send the supplied values off-site.
  if (req.kind === 'click' && e.form && e.matches('button:not([type]),button[type=submit],input[type=submit],input[type=image]')) {
    try {
      if (new URL(e.formAction || e.form.action, location.href).origin !== location.origin) return null;
    } catch (err) { return null; }
  }

  if (req.realInput && point) return { point };

  if (req.kind === 'fill') {
    const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(e), 'value')?.set;
    if (setter) setter.call(e, req.text); else e.value = req.text;
    e.dispatchEvent(new Event('input', { bubbles: true }));
    e.dispatchEvent(new Event('change', { bubbles: true }));
    return { done: true };
  }
  e.click();
  return { done: true };
})
