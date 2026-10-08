# Production Readiness Checklist (PC-*)

Coded checklist items used by `researcher` worker in Phase 2(b). Each item is
one line. Columns: Web | Mobile | Backend applicability. Deeper sources are
the parked skills at `~/.claude/skills-parked/{cso,harden,audit}/SKILL.md`
(see their headers for the full rubric).

| Code         | Item                                                                                | Web | Mobile | Backend |
|--------------|-------------------------------------------------------------------------------------|:---:|:------:|:-------:|
| PC-SEC-001   | No secrets committed (API keys, tokens, passwords)                                  | Y   | Y      | Y       |
| PC-SEC-002   | Auth on every mutating endpoint; auth middleware present                            | Y   | Y      | Y       |
| PC-SEC-003   | OWASP Top 10 sweep clean for the stack                                              | Y   | Y      | Y       |
| PC-SEC-004   | CSRF protection on state-changing web forms                                         | Y   | -      | -       |
| PC-SEC-005   | HTTPS-only; secure + httpOnly cookies                                              | Y   | -      | Y       |
| PC-SEC-006   | Input validation on every external boundary (forms, API, env)                       | Y   | Y      | Y       |
| PC-SEC-007   | Output encoding for HTML/JS/SQL contexts                                            | Y   | Y      | Y       |
| PC-SEC-008   | Rate limiting on auth + public endpoints                                            | Y   | Y      | Y       |
| PC-SEC-009   | Dependencies pinned; CVE audit clean                                                | Y   | Y      | Y       |
| PC-SEC-010   | STRIDE threat model reviewed for new architecture                                   | Y   | Y      | Y       |
| PC-SEC-011   | Mobile keychain/keystore usage for any local secret                                 | -   | Y      | -       |
| PC-OPS-001   | `.env.example` present; real secrets live in secret store                           | Y   | Y      | Y       |
| PC-OPS-002   | CI pipeline runs tests + lint on PR                                                 | Y   | Y      | Y       |
| PC-OPS-003   | Dockerfile present; image builds reproducibly                                       | Y   | Y      | Y       |
| PC-OPS-004   | Health route (`/health`) returns 200 with status                                    | Y   | -      | Y       |
| PC-OPS-005   | Structured logs (JSON or key=value) with request ID                                 | Y   | Y      | Y       |
| PC-OPS-006   | Error tracking (Sentry/Bugsnag/Rollbar) wired                                       | Y   | Y      | Y       |
| PC-OPS-007   | Backup scripts for primary datastore exist and tested                               | Y   | -      | Y       |
| PC-OPS-008   | Rollback procedure documented                                                       | Y   | Y      | Y       |
| PC-OPS-009   | Runbook for common incidents exists                                                 | Y   | Y      | Y       |
| PC-OPS-010   | Monitoring + alerting wired (uptime, error rate, saturation)                        | Y   | Y      | Y       |
| PC-OPS-011   | Mobile crash reporting wired (Crashlytics/Sentry-mobile)                            | -   | Y      | -       |
| PC-OPS-012   | Mobile OTA / staged rollout mechanism documented                                     | -   | Y      | -       |
| PC-DATA-001  | Migrations are reversible (or `down` provided)                                      | Y   | -      | Y       |
| PC-DATA-002  | DB connection pooling configured                                                    | Y   | -      | Y       |
| PC-DATA-003  | PII fields identified; encryption at rest for sensitive columns                     | Y   | Y      | Y       |
| PC-DATA-004  | Soft delete or audit log for destructive ops                                        | Y   | -      | Y       |
| PC-DATA-005  | Data retention policy documented                                                    | Y   | Y      | Y       |
| PC-DATA-006  | GDPR/CCPA delete + portability endpoints extracted                                 | Y   | Y      | Y       |
| PC-DATA-007  | Mobile offline storage uses encrypted store (SQLCipher/Room encrypted)              | -   | Y      | -       |
| PC-DATA-008  | Local user data clearable from settings                                              | -   | Y      | -       |
| PC-DATA-009  | Migration safety check on empty + populated DB                                       | Y   | -      | Y       |
| PC-UX-001    | Onboarding / first-run experience for new users                                     | Y   | Y      | -       |
| PC-UX-002    | Empty states for lists/tables/dashboards                                             | Y   | Y      | -       |
| PC-UX-003    | Error states surfaced (network, validation, server)                                 | Y   | Y      | -       |
| PC-UX-004    | Long-content overflow handled (names, descriptions, titles)                         | Y   | Y      | -       |
| PC-UX-005    | Accessibility: contrast, focus indicators, keyboard nav (WCAG AA baseline)          | Y   | Y      | -       |
| PC-UX-006    | Responsive across breakpoints (web) or device sizes (mobile)                         | Y   | Y      | -       |
| PC-UX-007    | Loading skeletons / spinners; not blank screens                                     | Y   | Y      | -       |
| PC-UX-008    | RTL layout tested (Arabic/Hebrew)                                                   | Y   | Y      | -       |
| PC-UX-009    | Touch targets >= 44pt; click targets >= 24px                                        | Y   | Y      | -       |
| PC-I18N-001  | Strings extracted to resource bundles / `.arb`                                      | Y   | Y      | Y       |
| PC-I18N-002  | At least English + Arabic locale complete                                           | Y   | Y      | Y       |
| PC-I18N-003  | Number/date/currency formatting locale-aware                                        | Y   | Y      | Y       |
| PC-I18N-004  | bidi-safe UI: no mixing direction glitches in mixed-language strings                 | Y   | Y      | -       |
| PC-I18N-005  | Pluralization handled by locale rules, not hardcoded n>1                            | Y   | Y      | -       |
| PC-LEGAL-001 | Privacy policy page present and reachable                                           | Y   | Y      | -       |
| PC-LEGAL-002 | Terms of service page present and reachable                                         | Y   | Y      | -       |
| PC-LEGAL-003 | Cookie consent / privacy controls surfaced on first visit                           | Y   | -      | -       |
| PC-LEGAL-004 | App store metadata: privacy nutrition label, support URL                            | -   | Y      | -       |
| PC-LEGAL-005 | License attribution for any embedded fonts / OSS components                          | Y   | Y      | Y       |
| PC-LEGAL-006 | Children compliance (COPPA / store age-gate) where applicable                       | Y   | Y      | -       |
| PC-TEST-001  | Test suite runs green on main                                                       | Y   | Y      | Y       |
| PC-TEST-002  | Critical paths covered by integration or e2e tests                                  | Y   | Y      | Y       |
| PC-TEST-003  | TDD discipline observed (failing test first) on new code                            | Y   | Y      | Y       |
| PC-TEST-004  | No skipped / `.only` / `.skip` tests in shipped code                                | Y   | Y      | Y       |
| PC-TEST-005  | CI gates merges on test failure                                                     | Y   | Y      | Y       |
| PC-TEST-006  | Load test or perf budget recorded for hot paths                                     | Y   | Y      | Y       |
| PC-TEST-007  | Mobile UI tests cover core flows (Maestro/XCUITest / Espresso)                      | -   | Y      | -       |
| PC-TEST-008  | Lint + type check pass in CI                                                         | Y   | Y      | Y       |
| PC-TEST-009  | Reviewer pass ran on recent feature work; no P0/P1 findings open                    | Y   | Y      | Y       |
| PC-A11Y-001  | axe / lighthouse accessibility >= 95                                                | Y   | Y      | -       |
| PC-A11Y-002  | Semantic HTML / native roles used (not div-soup)                                    | Y   | Y      | -       |
| PC-A11Y-003  | Alt text for images; captions for media                                             | Y   | Y      | -       |
| PC-A11Y-004  | Form fields have labels; errors announced                                           | Y   | Y      | -       |
| PC-PERF-001  | LCP < 2.5s on representative device/network                                         | Y   | -      | -       |
| PC-PERF-002  | Bundle size budget enforced                                                          | Y   | Y      | -       |
| PC-PERF-003  | Image optimization (modern formats, responsive `srcset`)                            | Y   | -      | -       |
| PC-PERF-004  | Cold start < target (mobile native, serverless)                                     | Y   | Y      | Y       |
| PC-PERF-005  | DB queries have indexes for hot lookups; no N+1 in hot paths                        | Y   | -      | Y       |
| PC-EDGE-001  | Network offline handling (graceful degradation, retry)                                | Y   | Y      | Y       |
| PC-EDGE-002  | Timeout handling on every external call                                              | Y   | Y      | Y       |
| PC-EDGE-003  | Concurrency / race condition tests for shared state                                  | Y   | Y      | Y       |
| PC-EDGE-004  | Boundary inputs covered: empty, max-length, unicode/emoji, RTL                      | Y   | Y      | Y       |
| PC-EDGE-005  | Retry/backoff strategy defined for downstream failures                              | Y   | Y      | Y       |
| PC-OBS-001   | Dashboards for golden signals (latency, traffic, errors, saturation)                | Y   | -      | Y       |
| PC-OBS-002   | On-call rotation or escalation contact documented                                  | Y   | -      | Y       |

Total: 78 items across 9 categories.

## Deeper sources

- `~/.claude/skills-parked/cso/SKILL.md` — security rubric (OWASP, STRIDE)
- `~/.claude/skills-parked/harden/SKILL.md` — edge cases / i18n / overflow
- `~/.claude/skills-parked/audit/SKILL.md` — accessibility / performance