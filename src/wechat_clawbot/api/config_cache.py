"""Per-user getConfig cache with TTL and exponential-backoff retry on failure."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from wechat_clawbot.api.client import WeixinApiOptions, get_config

if TYPE_CHECKING:
    from collections.abc import Callable

_CONFIG_CACHE_TTL_MS = 24 * 60 * 60 * 1000
_CONFIG_CACHE_INITIAL_RETRY_MS = 2_000
_CONFIG_CACHE_MAX_RETRY_MS = 60 * 60 * 1000


@dataclass
class CachedConfig:
    typing_ticket: str = ""


@dataclass
class _ConfigCacheEntry:
    config: CachedConfig
    ever_succeeded: bool
    next_fetch_at: float  # ms timestamp
    retry_delay_ms: int


class WeixinConfigManager:
    """Per-user ``getConfig`` cache with periodic random refresh (within 24h)
    and exponential-backoff retry (up to 1h) on failure."""

    def __init__(self, api_opts: WeixinApiOptions, log: Callable[[str], None]) -> None:
        self._api_opts = api_opts
        self._log = log
        self._cache: dict[str, _ConfigCacheEntry] = {}

    async def get_for_user(self, user_id: str, context_token: str | None = None) -> CachedConfig:
        import random

        now = time.time() * 1000
        entry = self._cache.get(user_id)
        should_fetch = entry is None or now >= entry.next_fetch_at

        if should_fetch:
            fetch_ok = False
            try:
                resp = await get_config(
                    opts=self._api_opts,
                    ilink_user_id=user_id,
                    context_token=context_token,
                )
                if resp.ret == 0:
                    self._cache[user_id] = _ConfigCacheEntry(
                        config=CachedConfig(typing_ticket=resp.typing_ticket or ""),
                        ever_succeeded=True,
                        next_fetch_at=now + random.random() * _CONFIG_CACHE_TTL_MS,
                        retry_delay_ms=_CONFIG_CACHE_INITIAL_RETRY_MS,
                    )
                    status = "refreshed" if entry and entry.ever_succeeded else "cached"
                    self._log(f"[weixin] config {status} for {user_id}")
                    fetch_ok = True
            except Exception as e:
                self._log(f"[weixin] getConfig failed for {user_id} (ignored): {e}")

            if not fetch_ok:
                prev_delay = entry.retry_delay_ms if entry else _CONFIG_CACHE_INITIAL_RETRY_MS
                next_delay = min(prev_delay * 2, _CONFIG_CACHE_MAX_RETRY_MS)
                if entry:
                    entry.next_fetch_at = now + next_delay
                    entry.retry_delay_ms = next_delay
                else:
                    self._cache[user_id] = _ConfigCacheEntry(
                        config=CachedConfig(),
                        ever_succeeded=False,
                        next_fetch_at=now + _CONFIG_CACHE_INITIAL_RETRY_MS,
                        retry_delay_ms=_CONFIG_CACHE_INITIAL_RETRY_MS,
                    )

        cached = self._cache.get(user_id)
        return cached.config if cached else CachedConfig()
