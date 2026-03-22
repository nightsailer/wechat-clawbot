"""Sensitive-data masking helpers for safe logging."""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse

_DEFAULT_BODY_MAX_LEN = 200
_DEFAULT_TOKEN_PREFIX_LEN = 6


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
    """Truncate a JSON body string for safe logging."""
    if not body:
        return "(empty)"
    if len(body) <= max_len:
        return body
    return f"{body[:max_len]}…(truncated, totalLen={len(body)})"


def redact_url(raw_url: str) -> str:
    """Strip query string from a URL, keeping only origin + pathname."""
    try:
        parsed = urlparse(raw_url)
        clean = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
        return f"{clean}?<redacted>" if parsed.query else clean
    except Exception:
        return truncate(raw_url, 80)
