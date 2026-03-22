"""Per-bot debug mode toggle, persisted to disk with in-memory cache."""

from __future__ import annotations

import contextlib
import json
from typing import TYPE_CHECKING

from wechat_clawbot.storage.state_dir import resolve_state_dir
from wechat_clawbot.util.logger import logger

if TYPE_CHECKING:
    from pathlib import Path

# In-memory cache so is_debug_mode() (called per-message on hot path) avoids disk I/O.
_cached_state: dict[str, bool] | None = None


def _resolve_debug_mode_path() -> Path:
    return resolve_state_dir() / "openclaw-weixin" / "debug-mode.json"


def _load_state_from_disk() -> dict[str, bool]:
    try:
        raw = _resolve_debug_mode_path().read_text("utf-8")
        parsed = json.loads(raw)
        if parsed and isinstance(parsed.get("accounts"), dict):
            return parsed["accounts"]
    except Exception:
        pass
    return {}


def _load_state() -> dict[str, bool]:
    """Return debug-mode state, preferring the in-memory cache."""
    global _cached_state
    if _cached_state is None:
        _cached_state = _load_state_from_disk()
    return _cached_state


def _save_state(accounts: dict[str, bool]) -> None:
    global _cached_state
    file_path = _resolve_debug_mode_path()
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps({"accounts": accounts}, indent=2), "utf-8")
    _cached_state = accounts


def toggle_debug_mode(account_id: str) -> bool:
    """Toggle debug mode for a bot account. Returns the new state."""
    state = _load_state().copy()
    next_val = not state.get(account_id, False)
    state[account_id] = next_val
    try:
        _save_state(state)
    except Exception as e:
        logger.error(f"debug-mode: failed to persist state: {e}")
        # Update in-memory cache even if disk write fails
        global _cached_state
        _cached_state = state
    return next_val


def is_debug_mode(account_id: str) -> bool:
    """Check whether debug mode is active for a bot account."""
    return _load_state().get(account_id, False)


def _reset_for_test() -> None:
    """Reset internal state (for tests only)."""
    global _cached_state
    _cached_state = None
    with contextlib.suppress(FileNotFoundError):
        _resolve_debug_mode_path().unlink()
