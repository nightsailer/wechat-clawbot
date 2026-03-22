"""Session expiration management — pause all API calls for an account after session timeout."""

from __future__ import annotations

import math
import time

from wechat_clawbot.util.logger import logger

SESSION_EXPIRED_ERRCODE = -14
_SESSION_PAUSE_DURATION_MS = 60 * 60 * 1000  # 1 hour

_pause_until_map: dict[str, float] = {}


def pause_session(account_id: str) -> None:
    """Pause all API calls for *account_id* for one hour."""
    until = time.time() * 1000 + _SESSION_PAUSE_DURATION_MS
    _pause_until_map[account_id] = until
    from datetime import datetime, timezone

    logger.info(
        f"session-guard: paused accountId={account_id} "
        f"until={datetime.fromtimestamp(until / 1000, tz=timezone.utc).isoformat()} "
        f"({_SESSION_PAUSE_DURATION_MS // 1000}s)"
    )


def is_session_paused(account_id: str) -> bool:
    """Return ``True`` when the bot is still within its one-hour cooldown."""
    until = _pause_until_map.get(account_id)
    if until is None:
        return False
    if time.time() * 1000 >= until:
        _pause_until_map.pop(account_id, None)
        return False
    return True


def get_remaining_pause_ms(account_id: str) -> int:
    """Milliseconds remaining until the pause expires (0 when not paused)."""
    until = _pause_until_map.get(account_id)
    if until is None:
        return 0
    remaining = until - time.time() * 1000
    if remaining <= 0:
        _pause_until_map.pop(account_id, None)
        return 0
    return int(remaining)


def assert_session_active(account_id: str) -> None:
    """Raise if the session is currently paused."""
    remaining = get_remaining_pause_ms(account_id)
    if remaining > 0:
        remaining_min = math.ceil(remaining / 60_000)
        raise RuntimeError(
            f"session paused for accountId={account_id}, "
            f"{remaining_min} min remaining (errcode {SESSION_EXPIRED_ERRCODE})"
        )


def _reset_for_test() -> None:
    """Reset internal state (for tests only)."""
    _pause_until_map.clear()
