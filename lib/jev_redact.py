"""Secret redaction for anything that leaves the machine (LLM / HTTP payloads, decision logs).

Stdlib only, no I/O. Shared by every caller that talks to an outside service: run the
whole request body through `redact()` right before it is serialised, and never send when
that raises (fail closed).

Two layers:
  1. Structure: in a dict, a string value whose key names a secret (api_key, *_TOKEN,
     password, authorization, cookie, ...) is replaced outright.
  2. Text: every string is scanned for known credential formats (OpenAI/OpenRouter/Anthropic
     `sk-...`, GitHub `ghp_`/`github_pat_`, AWS `AKIA`, Slack `xox*`, Google `AIza`, Stripe,
     Hugging Face, npm, GitLab, JWTs, PEM private keys), bearer/basic auth headers,
     credentials in URLs, secret-named KEY=VALUE assignments, and long high-entropy tokens.

Masks keep the shape a reviewer needs ("OPENROUTER_API_KEY=[REDACTED]", "Bearer [REDACTED]")
and drop the value. Variable names stay visible; values never do.
"""
from __future__ import annotations

import math
import re
from collections import Counter

MASK = "[REDACTED]"

# Names that mean "the value is a credential": *KEY, *SECRET, *TOKEN, *PASSWORD, ...
_SECRET_NAME = (
    r"(?:[A-Za-z0-9]+[_.-])*"
    r"(?:api[_.-]?key|apikey|access[_.-]?key|secret[_.-]?key|private[_.-]?key|client[_.-]?secret"
    r"|secret|token|access[_.-]?token|refresh[_.-]?token|auth[_.-]?token|passw(?:or)?d|pwd|passphrase"
    r"|credentials?|session[_.-]?(?:id|token|key)|cookie|authorization|bearer|signing[_.-]?key"
    r"|[A-Za-z0-9]*_key)"
)
SECRET_KEY_RE = re.compile(rf"^{_SECRET_NAME}$", re.I)
# Keys that look secret-ish but are just counters / config ("max_tokens", "token_count").
_NOT_SECRET_KEY = re.compile(r"(?:^|[_.-])(?:max|min|num|count|len|length|limit|budget|usage)(?:[_.-]|$)|tokens$", re.I)

_PATTERNS = [
    # PEM private keys (whole block, or a truncated head).
    (re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)", re.S),
     lambda m: "-----BEGIN PRIVATE KEY-----" + MASK + "-----END PRIVATE KEY-----"),  # secret-scan:allow (mask for PEM blocks, not a key)
    # Authorization headers / bearer tokens: keep the scheme.
    (re.compile(r"(?i)\b(bearer|basic|token)(\s+)([A-Za-z0-9._~+/=-]{12,})"),
     lambda m: f"{m.group(1)}{m.group(2)}{MASK}"),
    # Credentials embedded in URLs: scheme://user:password@host
    (re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^/\s:@\"']+:)([^@\s/\"']+)@"),
     lambda m: f"{m.group(1)}{MASK}@"),
    # Secret-named query parameters.
    (re.compile(r"(?i)([?&](?:access_token|refresh_token|id_token|token|api[_-]?key|apikey|key|secret|"
                r"client_secret|password|passwd|sig|signature|auth|code)=)([^&\s#\"'<>]+)"),
     lambda m: f"{m.group(1)}{MASK}"),
    # Known vendor key formats.
    (re.compile(r"\bsk-(?:or-|ant-|proj-|svcacct-|admin-)?[A-Za-z0-9_-]{16,}"), MASK),  # OpenAI/OpenRouter/Anthropic
    (re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{16,}"), MASK),               # Stripe
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}"), MASK),  # GitHub
    (re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA)[0-9A-Z]{16}\b"), MASK),                # AWS access key id
    (re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}|\bxapp-[A-Za-z0-9-]{10,}"), MASK),     # Slack
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}"), MASK),                                      # Google API key
    (re.compile(r"\bya29\.[0-9A-Za-z_-]{20,}"), MASK),                                   # Google OAuth token
    (re.compile(r"\bhf_[A-Za-z0-9]{30,}"), MASK),                                        # Hugging Face
    (re.compile(r"\bnpm_[A-Za-z0-9]{36}\b"), MASK),                                      # npm
    (re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}"), MASK),                                   # GitLab
    (re.compile(r"\bxai-[A-Za-z0-9]{20,}"), MASK),                                       # xAI
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), MASK),  # JWT
    # NAME=value / "name": "value" / name: value for secret-shaped names (quoted or not).
    # Values that are references, not secrets ($VAR, os.environ[...], process.env.X, env(...)) are kept.
    (re.compile(
        rf"(?i)((?:(?<=\\[nrt])|\b){_SECRET_NAME}\b\\?[\"']?\s*(?::|=|=>)\s*\\?[\"']?)"
        r"(?!\$|os\.|process\.env|env\(|getenv|\{\{|<|\[REDACTED\]|None\b|null\b|true\b|false\b|undefined\b|(?i:bearer|basic|token)\s)"
        r"([^\s\"'`,;&\\)}\]]{6,})"),
     lambda m: f"{m.group(1)}{MASK}"),
]

_TOKEN_RE = re.compile(r"[A-Za-z0-9+/_=.-]{32,}")


def _entropy(s: str) -> float:
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in Counter(s).values())


def _high_entropy(m: re.Match) -> str:
    tok = m.group(0)
    if MASK in tok or "/" in tok.strip("/") and tok.count("/") > 2:  # paths, not keys
        return tok
    core = tok.strip("=.-_")
    classes = sum(bool(re.search(p, core)) for p in (r"[a-z]", r"[A-Z]", r"[0-9]"))
    if len(core) >= 32 and classes == 3 and _entropy(core) >= 4.0:
        return MASK
    return tok


def redact_text(text: str) -> str:
    """Mask every secret-shaped substring of `text`."""
    for rx, repl in _PATTERNS:
        text = rx.sub(repl, text)
    return _TOKEN_RE.sub(_high_entropy, text)


def is_secret_key(name) -> bool:
    return isinstance(name, str) and bool(SECRET_KEY_RE.match(name)) and not _NOT_SECRET_KEY.search(name)


def redact(obj):
    """Deep copy of `obj` (str / dict / list / scalars) with every secret masked."""
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            # A secret-named key with a token-like value (no spaces) is masked outright;
            # prose under such a key (e.g. a choice option named "token") is still text-scanned.
            if is_secret_key(k) and isinstance(v, str) and len(v.strip()) >= 4 and not re.search(r"\s", v.strip()):
                out[k] = MASK
            else:
                out[k] = redact(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [redact(v) for v in obj]
    return obj


# Files whose contents must never be read into a prompt / state (KB sensitive-path list).
SENSITIVE_PATH_RE = re.compile(
    r"(?:^|/)\.env(?:\.(?!example$|sample$|template$|dist$)[^/]+)?$"
    r"|(?:^|/)\.ssh/|(?:^|/)id_(?:rsa|dsa|ecdsa|ed25519)$|\.(?:pem|key|p12|pfx|keystore|jks)$"
    r"|(?:^|/)\.aws/credentials$|(?:^|/)\.config/gcloud/|(?:^|/)\.kube/config$|(?:^|/)\.docker/config\.json$"
    r"|(?:^|/)\.(?:netrc|npmrc|pypirc|git-credentials)$|(?:^|/)Keychains/"
    r"|(?:^|/)credentials[^/]*\.json$|(?:^|/)secrets\.(?:ya?ml|json)$|auth\.json$|(?:^|/)\.config/typesafe/api_key$"
)


def is_sensitive_path(path: str) -> bool:
    return bool(SENSITIVE_PATH_RE.search(str(path).replace("\\", "/")))
