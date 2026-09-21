// Post-input wait for jev-browse, replacing a flat 400 ms sleep after every action.
// Called as SETTLE + '(' + JSON.stringify(req) + ')' with awaitPromise; req = { node, kind }.
//
// Typing into a combobox waits for its suggestions to actually paint (capped at 200 ms) — a typed query
// whose autocomplete never appeared is the classic reason the next step picks the wrong element. Anything
// else gets two animation frames, capped at 50 ms. Lightpanda has no rAF, so it falls through to the cap.
((req) => new Promise((resolve) => {
  const cache = window.__jevBrowse;
  const field = cache && cache.nodes.get(req.node);
  const autocomplete = req.kind === 'fill' && field
    && (field.getAttribute('role') === 'combobox' || field.getAttribute('aria-autocomplete')
      || field.getAttribute('aria-controls') || field.getAttribute('aria-owns'));
  let frames = 0, stopped = false;
  const finish = () => { if (!stopped) { stopped = true; resolve(); } };
  setTimeout(finish, autocomplete ? 200 : 50);
  if (typeof requestAnimationFrame !== 'function') return;
  const suggestionsVisible = () => {
    const ids = ((field.getAttribute('aria-controls') || field.getAttribute('aria-owns') || '')
      .split(/\s+/).filter(Boolean));
    const roots = ids.length ? ids.map((id) => document.getElementById(id)).filter(Boolean) : [document];
    return roots.flatMap((root) => [...root.querySelectorAll('[role="option"]')]).some((o) => {
      const r = o.getBoundingClientRect();
      return r.width && r.height && r.bottom > 0 && r.top < innerHeight
        && (typeof o.checkVisibility !== 'function'
          || o.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }));
    });
  };
  const ready = () => {
    if (stopped) return;
    if (++frames >= 2 && (!autocomplete || suggestionsVisible())) finish();
    else requestAnimationFrame(ready);
  };
  requestAnimationFrame(ready);
}))
