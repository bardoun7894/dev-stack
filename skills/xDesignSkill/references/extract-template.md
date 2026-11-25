# Design extract: <subject>

**Date:** <YYYY-MM-DD> · **For:** <project, screen> · **Platform:** web | mobile · **Languages:** <AR RTL / EN / FR>
**Project design truth:** `<DESIGN.md | none>` · **Folder:** `design/inspiration/<date>-x-<slug>/`

## References (from manifest.json)

| # | Post | Author | Date | Files | Same project type? | Why it is close |
|---|---|---|---|---|---|---|
| 1 | [<post text>](<url>) | @<handle> | <date> | `01-….jpg` + tiles | no (healthcare) | <one line> |

## What the reference does

### Tokens

| Token | Value | Source |
|---|---|---|
| Page background | `#......` | palette, <share>% |
| Surface (cards) | `#......` | palette |
| Primary | `#......` | palette |
| Accent | about `#......` | by eye (too small to sample) |
| Text strong / muted | `#......` / `#......` | palette / by eye |
| Radius: card / control / pill | <px> / <px> / full | measured on tile t<n>, image is <W> px wide |
| Type: display / title / body / caption | <px, weight> … | measured on tile |
| Card gap / card padding | <px> / <px> | measured on tile |
| Shadow / border | <description> | by eye |

### Layout skeleton

<Grid, columns, nav model (top pill bar, left rail, …), hero or header band, card rows, what
is sticky. One short ASCII sketch if it helps.>

### Components

| Component | Anatomy | States seen |
|---|---|---|
| KPI card | icon + label, big number, delta chip, sparkline, corner action | default, <hover in frame f04> |

### Charts

| Chart | Encodes | Notes |
|---|---|---|
| <ring, bars, area> | <what> | <colors, labels, legend position> |

### Motion and interaction (video posts only)

| Moment | Frames | What changes | Duration (est.) |
|---|---|---|---|
| <filter switch> | f03 → f05 | <bars regrow, number counts up> | <~300 ms> |

## The same structure for <project>

| Reference widget | Becomes | Data it shows | Decision |
|---|---|---|---|
| Bed Occupancy card | Fleet in service | trucks on the road / total, today | adopt |
| 3D organ hero art | (none) | | drop |

Screen outline for the project, top to bottom, with the real labels in the project's language.

## Decisions

| Code | Change | Decision | Rule that decides it |
|---|---|---|---|
| R1 | <pill top nav with solid active pill> | adopt | <fits 6 sections; DESIGN.md has no nav rule> |
| R2 | <blue gradient hero band> | adapt to <brand color>, flat | <DESIGN.md palette; no purple gradients> |
| R3 | <glass 3D illustration> | reject | <not ours to reuse; imagery policy> |

## Risks

- **RK1: <low contrast of white text on light blue / RTL mirroring / dense cards on mobile>.** Mitigation: <one line>.

## Hand-off brief

Screen: <name>. Build against <DESIGN.md tokens | the token table above>. Follow the screen
outline and R<adopted codes>. Reference files for layout and spacing only: `01-…-t1.jpg`,
`01-…-t3.jpg`. Do not reproduce the reference, its name, art or copy. Languages: <…>.
Acceptance: <3 checks, e.g. every card shows a real project number; contrast AA; RTL mirrored>.
