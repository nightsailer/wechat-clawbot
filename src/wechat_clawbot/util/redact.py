"""Sensitive-data masking helpers for safe logging."""

from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

_DEFAULT_BODY_MAX_LEN = 200
_DEFAULT_TOKEN_PREFIX_LEN = 6

# Field names whose values should be masked in logged JSON bodies.
_SENSITIVE_FIELDS_RE = re.compile(
    r'"(context_token|bot_token|token|authorization|Authorization)"\s*:\s*"[^"]*"'
)


def truncate(s: str | None, max_len: int) -> str:
    """Truncate *s*, appending a length indicator when trimmed."""
    if not s:
        return ""
    if len(s) <= max_len:
        return s
    return f"{s[:max_len]}…(len={len(s)})"


def redact_token(token: str | None, prefix_len: int = _DEFAULT_TOKEN_PREFIX_LEN) -> str:
    """Show only the first few chars of a token plus its total length."""
    if not token:
        return "(none)"
    if len(token) <= prefix_len:
        return f"****(len={len(token)})"
    return f"{token[:prefix_len]}…(len={len(token)})"


def redact_body(body: str | None, max_len: int = _DEFAULT_BODY_MAX_LEN) -> str:
    """Redact known sensitive fields, then truncate for safe logging."""
    if not body:
        return "(empty)"
    # Mask values of known sensitive JSON keys: "key":"value" → "key":"<redacted>"
    redacted = _SENSITIVE_FIELDS_RE.sub(r'"\1":"<redacted>"', body)
    if len(redacted) <= max_len:
        return redacted
    return f"{redacted[:max_len]}…(truncated, totalLen={len(redacted)})"


def redact_url(raw_url: str) -> str:
    """Strip query string from a URL, keeping only origin + pathname."""
    try:
        parsed = urlparse(raw_url)
        clean = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
        return f"{clean}?<redacted>" if parsed.query else clean
    except Exception:
        return truncate(raw_url, 80)
