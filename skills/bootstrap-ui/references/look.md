# Why a Bootstrap app looks "default", and the fixes

People recognise stock Bootstrap at a glance. Each tell below has the fix the templates apply. Generic AI-UI tells (purple gradients, glows, emoji labels) belong to the `unslop` skill; this list is Bootstrap-specific.

| Tell | Why it reads as default | Fix |
|---|---|---|
| `#0d6efd` primary on every button, link, switch and pill | The best-known blue on the web | Brand primary via `$primary` or `bs-theme.css`. The CSS path must re-point all 23 hard-coded spots |
| Pure white page, white cards, 1px grey borders everywhere | No layers, so everything sits at the same depth | Light grey canvas (`--bs-body-bg: #f5f6f8`), white cards with `box-shadow-sm`, borders one step lighter |
| Bold black table headers | Shouts louder than the data | `thead th`: secondary color, small size, weight 600, no wrap |
| `0.375rem` radius on everything | Bootstrap's exact corner | Controls 0.5rem, cards 0.75rem, modals 1rem: one scale, larger as the surface grows |
| System font stack, 16px everywhere | Generic and loose for dense admin screens | Inter (Latin) and IBM Plex Sans Arabic (RTL) at a 15px base, line-height 1.55, headings 600 with slight negative tracking (never on Arabic) |
| Cyan `info` alerts and yellow `#ffc107` warning badges | Dated palette; white text fails on the yellow | Calm blue info tint; a darker warning that carries white text at 4.5:1 or better |
| Glow focus ring at 0.25rem and 25% opacity | Heavy, blurry halo | 0.2rem ring at 22% opacity in the brand color, border to a mid tint |
| `btn-lg` everywhere, or default padding on dense toolbars | Toy proportions | `btn` 0.5rem by 1rem at weight 500; `btn-sm` in tables and toolbars |
| Cards with `card-header` grey bars | 2013 panel look | Transparent header, weight 600, same surface |
| Mixed icon sets (Font Awesome 4 + Bootstrap Icons + emoji) | Inconsistent stroke and size | One set. Bootstrap Icons fits; Font Awesome 6 if the theme already ships it. Same size class everywhere |
| Inline `style="color:#..."` scattered in Blade | Colors drift by page | Utilities (`text-body-secondary`, `text-bg-*`, `*-subtle`) or tokens. Doctor code `inline-hex` |
| Everything centered in a `container` on wide admin screens | Wasted width on 1440p | `container-fluid px-4` for admin, `container` for marketing pages |

## Layout patterns that look current

- **Page header:** H1 (`.h3`) plus a one-line muted subtitle on the left, actions on the right (secondary outline first, primary last). In RTL the order mirrors by itself with flex `me-auto`.
- **Stats row:** 4 cards with a muted label, the value at `fs-4 fw-semibold`, and the delta colored with `text-success`/`text-danger` (not a pill).
- **Data table in a card:**
  - `table-hover align-middle mb-0` inside `.table-responsive`;
  - status as `badge text-bg-*`;
  - amounts `text-end font-monospace`;
  - filters as `nav-pills` in the card header;
  - pagination and progress in the card footer.
- **Form in a card:**
  - label above the input (`form-label` weight 500);
  - help text through `aria-describedby`;
  - errors with `.is-invalid` plus `invalid-feedback`;
  - two short fields per row with `row g-3`;
  - the primary action full width, cancel as outline.
- **Modals:** title as `h6` in the header; destructive action as `btn-danger` on the end side; cancel as outline. Never a modal inside a modal.
- **Empty states:** one muted sentence plus the primary action. No illustrations that the app has nowhere else.

## Accessibility that Bootstrap leaves to you

Docs: getting-started/accessibility and forms.

- Every input gets a `<label for>`. Visually hidden labels use `.visually-hidden`. A placeholder is not a label.
- Icon-only buttons get `aria-label`, for example the `.btn-close` "Close".
- Color is never the only signal: badges carry text, invalid fields carry a message.
- Contrast: text needs 4.5:1. The Bootstrap docs warn that some default color combinations fall short. Stock 5.3.9 passed the pairs `contrast.py` checks, but brand colors often fail, so run it on every theme.
- Keep visible focus. Do not set `outline: 0` without a replacement ring; the templates replace it with the brand ring.
- `prefers-reduced-motion` is respected by Bootstrap transitions. Keep custom animations behind the same media query.

## Before and after evidence

The kitchen-sink admin screen (`scripts/kitchen_sink.py`) was rendered stock, themed, dark and RTL on 2026-11-19. The themed renders show:
- a layered canvas;
- muted table headers;
- brand primary on all components;
- a readable warning badge;
- calm info alerts;
- correct mirroring in Arabic (progress fill, input group, switch, pagination).

Render the client's own pages the same way before and after a change, and show the owner both images.
