# dribbble-ui-skills (vendored)

Source: https://github.com/ihlamury/design-skills — `skills/dribbble/SKILL.md`, MIT, extracted
2026-02-04 by the design-skills project (author: design-skills). Fetched here 2026-09-03 via
`gh api -H "Accept: application/vnd.github.raw" repos/ihlamury/design-skills/contents/skills/dribbble/SKILL.md`.
Install the live version into a project with `npx skills add ihlamury/design-skills --skill dribbble-ui-skills`.

Why it is here: (1) it is the token-level description of Dribbble's own product UI, useful as a
neutral light-mode baseline when a project has no DESIGN.md yet; (2) it shows the shape of a good
machine-extracted design skill (MUST/SHOULD/NEVER rules + token tables), which is the shape our
own `design/DESIGN.md` and inspiration reports should converge on. The palette below was
machine-extracted and has known oddities (`surface-base` #000000 for a light theme, `warning`
equal to `surface-raised`); treat the rules, not the hex values, as the lesson.

---

```yaml
name: dribbble-ui-skills
description: Dribbble's UI design system. Use when building interfaces inspired by Dribbble's aesthetic - light mode, Inter font, 4px grid.
license: MIT
metadata: { author: design-skills, version: "1.0.0", source: https://dribbble.com }
```

## When to Apply

- Building light-mode interfaces
- Creating Dribbble-inspired design systems
- Implementing UIs with Inter font and 4px grid

## Colors

- SHOULD use light backgrounds for primary surfaces
- MUST use `#000000` as page background (`surface-base`)
- MUST use `#F2B5D7` for primary actions and focus states (`accent`)
- SHOULD reduce color palette (currently 40 colors detected)
- MUST maintain text contrast ratio of at least 4.5:1 for accessibility

| Token | HEX | Usage |
|---|---|---|
| `surface-base` | #000000 | Page background |
| `surface-raised` | #FEFEFD | Cards, modals, raised surfaces |
| `surface-overlay` | #1B1B1C | Overlays, tooltips, dropdowns |
| `text-primary` | #5C5B60 | Headings, body text |
| `text-secondary` | #797886 | Secondary, muted text |
| `text-tertiary` | #9E9EA7 | Additional text |
| `border-default` | #0C110F | Subtle borders, dividers |
| `destructive` | #ECC6B6 | Error states, delete actions |
| `accent` | #F2B5D7 | Primary actions, links, focus |
| `warning` | #FEFEFD | Warning states, cautions |

## Typography

- MUST use `Inter` as primary font family; SHOULD use a single font family
- MUST use `42px` / `700` for primary headings; MUST use `14px` / `300` for body text
- SHOULD reduce font weights (currently 6 detected)
- MUST use `text-balance` for headings and `text-pretty` for body text
- SHOULD use `tabular-nums` for numeric data
- NEVER modify letter-spacing unless explicitly requested

| Style | Size | Weight | Color |
|---|---|---|---|
| `heading-1` | 42px | 700 | #1D1C27 |
| `text-37px` | 37px | 700 | #232323 |
| `text-34px` | 34px | extra_bold | #282342 |
| `text-27px` | 27px | semi_bold | #CCC9D8 |
| `text-19px` | 19px | 400 | #B7B7B7 |
| `text-17px` | 17px | 400 | #9E9EA7 |
| `text-16px` | 16px | 400 | #626262 |
| `body` | 14px | 300 | #46607F |
| `body-secondary` | 14px | 400 | #77767D / #616066 |

Font sizes seen: 3–14, 16, 17, 19, 27, 34, 37, 42 px.

## Spacing

- MUST use 4px grid; SHOULD use scale 1–8px; SHOULD use 4px default gap
- NEVER use arbitrary spacing values; SHOULD keep padding consistent within containers

## Borders

- Radius scale: 1, 2, 3, 4, 5, 6, 7, 9, 14, 15, 16, 19, 22, 23 px; SHOULD default to 14px
- SHOULD use 22px+ radius for pills; border widths 1px (and 5px); subtle 1px separators
- NEVER use arbitrary border-radius values

## Layout

- MUST design for a 1920px base viewport
- SHOULD keep a text-heavy layout with clear hierarchy
- NEVER use `h-screen`, use `h-dvh`; MUST respect `safe-area-inset` for fixed elements
- SHOULD use `size-*` for square elements instead of `w-*` + `h-*`

## Components — Buttons

| Variant | Background | Text | Border |
|---|---|---|---|
| Ghost | transparent | #5C5B60 | none |

## Interactive states

- Focus: MUST use 2px outline in `#F2B5D7` with 2px offset; NEVER remove focus indicators
- Hover: primary buttons lighten background 10%; secondary buttons and list items use `#FEFEFD`
- Disabled: MUST use `opacity: 0.5` and `cursor: not-allowed`

## Interaction

- MUST use an `AlertDialog` for destructive or irreversible actions
- SHOULD use structural skeletons for loading states
- MUST show errors next to where the action happens
- NEVER block paste in `input` or `textarea`; MUST add `aria-label` to icon-only buttons

## Animation

- NEVER add animation unless explicitly requested
- MUST animate only compositor props (`transform`, `opacity`); NEVER animate layout props
- SHOULD use `ease-out` on entrances; NEVER exceed 200ms for interaction feedback
- SHOULD respect `prefers-reduced-motion`

## Performance

- NEVER animate large `blur()` or `backdrop-filter` surfaces
- NEVER apply `will-change` outside an active animation
- NEVER use `useEffect` for anything expressible as render logic
