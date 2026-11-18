last_refreshed: 2026-10-08

# UI/UX + motion "wow" checklist

- Hero: one promise, one visual proof, one CTA; LCP element is the hero.
- Scroll storytelling: one idea per viewport; pin sparingly.
- Micro-interactions: hover, press, success; 100-300ms.
- Page transitions: shared-element or crossfade, never blocking.
- Loading: skeletons matching final layout, not spinners.
- Empty states: explain, show one action, show a sample.
- Typography scale: modular scale, max 2 families, tokens from DESIGN.md.
- RTL: mirrored layout, logical CSS properties, Arabic font metrics, no mirrored icons that carry direction-neutral meaning.
- Performance budget: LCP < 2.5s, INP < 200ms, animate transform/opacity only.
- `prefers-reduced-motion`: disable parallax/autoplay, keep state changes via opacity or instant.

## AI-era UI/UX
Seeded 2026-10-08, refresh via step 4b.
- Copilot, not autopilot: AI optional; assistant beside structured views, not an open chat box as main UI; visible sources, an action log, confirm before committing changes.
- Trust: show how the result was reached (source link or inputs, a confidence signal). Every suggestion has dismiss, edit and undo. Users can revert adaptive changes.
- Perceived speed: stream output. Each AI feature has 3 states: success, degraded, failure. Skeletons, not spinners.
- Generative/adaptive layouts stay stable between sessions, never surprising.
- Accessibility for streaming: ARIA live region on the response container, role=status on loaders, move focus to the finished answer, alt text on generated images.
- Motion: purposeful, 100-300ms, honour prefers-reduced-motion. Prefer interactive runtimes (Rive state machines, Spline/Hana embeds) over video when motion reacts to input. AI tools (Figma, Framer, Jitter) suggest transitions; a human reviews them.
- Avoid the generic "AI look" (gradient orbs, AI badges everywhere); design for the specific workflow. Bento layouts and refined glass are current; keep them calm.
- Mobile: voice as quick-action input with text alternatives; predictive shortcuts.
- Seed sources: uxpin.com/studio/blog/ui-ux-design-trends/ ; groovyweb.co/blog/ui-ux-design-trends-ai-apps-2026 ; fuselabcreative.com/ui-ux-design-trends-2026-modern-ui-trends-ux-trends-guide/ ; knubisoft.medium.com/ai-native-ux-in-2026-a-builders-guide-97cdb2ef1a7b ; aydesign.ai/blog/mobile-app-ui-ux-for-ai-products ; parachutedesign.ca/blog/ai-tools-for-web-designers/ ; jitter.video ; designwings.substack.com/p/biggest-uxui-design-updates-weekly

### Archived
Items whose sources are older than 12 months move here on refresh. Never delete.
(none yet)
