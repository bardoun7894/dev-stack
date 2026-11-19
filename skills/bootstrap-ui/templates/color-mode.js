/* color-mode.js: light / dark / auto for Bootstrap 5.3 (data-bs-theme on <html>).
   Load it INLINE at the top of <head>, before any CSS, so the page never flashes the wrong
   theme. Toggle buttons: <button data-bs-theme-value="light|dark|auto">. Stored per browser. */
(() => {
  const KEY = 'theme';
  const stored = () => { try { return localStorage.getItem(KEY); } catch { return null; } };
  const store = (v) => { try { localStorage.setItem(KEY, v); } catch { /* private mode */ } };
  const media = window.matchMedia('(prefers-color-scheme: dark)');
  const preferred = () => stored() || 'auto';
  const apply = (mode) => {
    const dark = mode === 'dark' || (mode === 'auto' && media.matches);
    document.documentElement.setAttribute('data-bs-theme', dark ? 'dark' : 'light');
  };
  const mark = (mode) => document.querySelectorAll('[data-bs-theme-value]').forEach((el) => {
    const on = el.getAttribute('data-bs-theme-value') === mode;
    el.classList.toggle('active', on);
    el.setAttribute('aria-pressed', String(on));
  });
  apply(preferred());
  media.addEventListener('change', () => { if (preferred() === 'auto') apply('auto'); });
  window.addEventListener('DOMContentLoaded', () => {
    mark(preferred());
    document.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-bs-theme-value]');
      if (!btn) return;
      const mode = btn.getAttribute('data-bs-theme-value');
      store(mode); apply(mode); mark(mode);
    });
  });
})();
