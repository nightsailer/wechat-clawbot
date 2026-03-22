"""Resolve the OpenClaw state directory."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_state_dir() -> Path:
    """Return the OpenClaw state directory (mirrors core logic).

    Precedence: ``$OPENCLAW_STATE_DIR`` > ``$CLAWDBOT_STATE_DIR`` > ``~/.openclaw``.
    """
    env = os.environ.get("OPENCLAW_STATE_DIR", "").strip()
    if env:
        return Path(env)
    env = os.environ.get("CLAWDBOT_STATE_DIR", "").strip()
    if env:
        return Path(env)
    return Path.home() / ".openclaw"
