---
name: cso
description: Chief Security Officer — run OWASP Top 10, STRIDE threat model, secret scan, and CVE audit over the repo. Triggers on "security audit", "security review", "check for vulns", "OWASP check", "secret scan", "/cso". Standalone — never auto-fires. Outputs a scored report with P0-P3 severity and a remediation punch list. Read-only; never modifies code.
allowed-tools: Bash Read Grep Glob
---

# cso — Chief Security Officer audit

Adversarial security sweep over the current repo. Read-only. Never edits code — hands findings to the `backend-engineer` or user for remediation.

## Scope

Four passes, each runs in parallel when possible:

1. **Secret scan** — committed credentials, tokens, keys
2. **Dependency CVE audit** — known vulnerable packages
3. **OWASP Top 10 code review** — language-appropriate patterns
4. **STRIDE threat model** — architecture-level risks

## Pass 1 — secret scan

```bash
# Prefer ripgrep (rg) — it auto-respects .gitignore so node_modules/vendor/etc.
# are excluded for free. Falls back to `find | grep` on systems without rg.
# BSD grep's --exclude-dir does NOT recurse nested dirs reliably on macOS;
# do not rely on it.

SECRET_RE='(api[_-]?key|secret|password|token|bearer|aws_access|private_key)[[:space:]]*[:=][[:space:]]*["\x27][A-Za-z0-9+/=_-]{20,}'

if command -v rg >/dev/null; then
  rg -n --no-heading -e "$SECRET_RE" -g '!node_modules/**' -g '!vendor/**' \
    -g '!.git/**' -g '!dist/**' -g '!build/**' -g '!.next/**' -g '!.venv/**' \
    -g '!__pycache__/**' -g '!coverage/**' -g '!target/**' \
    -g '*.{js,ts,jsx,tsx,py,php,rb,go,rs,java,kt,swift}' -g '.env*' | head -50
else
  find . -type f \( -name '*.js' -o -name '*.ts' -o -name '*.jsx' -o -name '*.tsx' \
        -o -name '*.py' -o -name '*.php' -o -name '*.rb' -o -name '*.go' \
        -o -name '*.rs' -o -name '*.java' -o -name '.env*' \) \
    -not -path '*/node_modules/*' -not -path '*/.git/*' -not -path '*/vendor/*' \
    -not -path '*/dist/*' -not -path '*/build/*' -not -path '*/.next/*' \
    -not -path '*/.venv/*' -not -path '*/__pycache__/*' -not -path '*/coverage/*' \
    -print0 2>/dev/null | xargs -0 grep -InE "$SECRET_RE" 2>/dev/null | head -50
fi

# Git history — files historically committed with sensitive extensions
git log --all --full-history --diff-filter=A --name-only -- "*.env*" "*.key" "*.pem" 2>/dev/null | grep -v '^$' | head -20

# Unprotected .env files in working tree
find . -type f -name '.env*' \
  -not -path '*/node_modules/*' -not -path '*/.git/*' \
  -not -path '*/vendor/*' -not -path '*/.venv/*'

# Heuristics miss entropy-based and format-specific secrets. For a real audit run:
#   gitleaks detect --source . --no-banner
#   trufflehog filesystem . --only-verified
```

Flag P0: plaintext production credentials in git history. P1: `.env` not in `.gitignore`. P2: placeholder-looking values that might be real.

## Pass 2 — dependency CVE audit

Language auto-detect from lockfiles:

| Lockfile | Command |
|---|---|
| `package-lock.json` / `bun.lock` / `pnpm-lock.yaml` / `yarn.lock` | `npm audit --audit-level=moderate` or `bun audit` |
| `composer.lock` | `composer audit` |
| `Pipfile.lock` / `poetry.lock` / `uv.lock` | `pip-audit` or `uv pip audit` |
| `Gemfile.lock` | `bundle audit` |
| `go.sum` | `govulncheck ./...` |
| `Cargo.lock` | `cargo audit` |

Classify: Critical → P0, High → P1, Moderate → P2, Low → P3.

## Pass 3 — OWASP Top 10 code review

Scan for language-specific patterns:

1. **Injection** — raw SQL concat, `eval`, `exec`, `shell=True`, `$_GET`/`$_POST` without escaping
2. **Broken auth** — no rate-limit on login, session in localStorage, JWT without expiry
3. **Sensitive data exposure** — cleartext password logging, no HTTPS enforcement
4. **XXE** — XML parser without `disable_entities` / external-DTD flag set
5. **Broken access control** — missing `@authorize`, route guards without role check, IDOR in `/:id` endpoints
6. **Security misconfig** — `DEBUG=true` committed, permissive CORS (`*`), missing CSP
7. **XSS** — `innerHTML` / `dangerouslySetInnerHTML` / `v-html` with user input; `render_template_string`
8. **Insecure deserialization** — `pickle.loads` / `unserialize` / `Marshal.load` on untrusted input
9. **Components with known vulns** — covered by pass 2
10. **Insufficient logging** — no audit trail on auth events, no failed-login tracking

For each hit: `file:line`, excerpt, OWASP category, severity, suggested fix.

## Pass 4 — STRIDE threat model

For each external surface (API endpoint, upload, webhook, auth flow), rate:

| Threat | Question |
|---|---|
| **S**poofing | Can an attacker impersonate this client/user? |
| **T**ampering | Can request/response be modified in flight? |
| **R**epudiation | Can the actor deny the action happened? |
| **I**nfo disclosure | What data leaks on success? On error? |
| **D**oS | What rate of requests kills this? |
| **E**levation of privilege | Can a low-priv user reach high-priv ops? |

Output one row per surface, one letter-grade per STRIDE threat.

## Final report format

```
# Security Audit — <repo> @ <sha>
Generated: <ISO>
Passes: secrets, deps, owasp, stride

## Score
P0 (critical):   N findings
P1 (high):       N findings
P2 (moderate):   N findings
P3 (low):        N findings

## Findings
### P0-01 — <title>
  File: path:line
  OWASP: A03 Injection / STRIDE: E
  Excerpt: <5 lines>
  Fix: <one-sentence remediation>

[... more findings ...]

## Remediation plan (ranked)
1. <P0 fix> — <effort estimate>
2. ...
```

## Rules

- **Read-only.** Never edit code. Never run migrations or anything with side effects.
- **Never execute found secrets.** Treat them as compromised; recommend rotation.
- **Explicit severity.** P0 = "fix today", P1 = "fix this sprint", P2 = "backlog", P3 = "nice-to-have".
- **No false confidence.** If a pass failed (tool missing, repo too big), say so in the report — don't silently pass.

## Pairs with

- `investigate` — dig into any P0/P1 finding root cause.
- `backend-engineer` subagent — hand off remediation work.
- `dogfood` — re-run after fixes to confirm the vuln is gone.
- `/ship` — blocks on unresolved P0s per the DevOps sign-off rule.
