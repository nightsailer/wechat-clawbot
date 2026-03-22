"""ID and temp filename generation utilities."""

from __future__ import annotations

import secrets
import time


def generate_id(prefix: str) -> str:
    """Generate a prefixed unique ID: ``{prefix}:{timestamp}-{8-char hex}``."""
    return f"{prefix}:{int(time.time() * 1000)}-{secrets.token_hex(4)}"


def temp_file_name(prefix: str, ext: str) -> str:
    """Generate a temporary file name: ``{prefix}-{timestamp}-{8-char hex}{ext}``."""
    return f"{prefix}-{int(time.time() * 1000)}-{secrets.token_hex(4)}{ext}"
