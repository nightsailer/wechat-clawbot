"""Shared poll-loop core for getUpdates-based message polling.

Provides ``poll_loop``, an async helper that wraps the common
retry / back-off / session-guard / sync-buf logic used by both the
gateway :mod:`wechat_clawbot.gateway.poller` and — potentially — the
standalone :mod:`wechat_clawbot.monitor.monitor` (which could be
migrated to use this in a future iteration).
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import anyio

from wechat_clawbot.api.client import get_updates
from wechat_clawbot.api.session_guard import (
    SESSION_EXPIRED_ERRCODE,
    get_remaining_pause_ms,
    is_session_paused,
    pause_session,
)
from wechat_clawbot.storage.sync_buf import load_get_updates_buf, save_get_updates_buf

if TYPE_CHECKING:
    from pathlib import Path

    from wechat_clawbot.api.types import GetUpdatesResp

logger = logging.getLogger(__name__)

MAX_CONSECUTIVE_FAILURES = 3
FAILURE_RETRY_DELAY = 2.0
FAILURE_BACKOFF_DELAY = 30.0
SESSION_PAUSE_POLL_DELAY = 60.0

# Callback type: receives the full getUpdates response for processing
MessageProcessor = Callable[["GetUpdatesResp"], Awaitable[None]]


async def poll_loop(
    *,
    account_id: str,
    base_url: str,
    token: str | None,
    sync_buf_path: Path,
    on_response: MessageProcessor,
    stop_event: anyio.Event,
) -> None:
    """Run a getUpdates poll loop until *stop_event* is set.

    Parameters
    ----------
    account_id:
        Used for session-guard pause/resume and logging.
    base_url:
        WeChat API base URL.
    token:
        Bot API token (may be ``None`` if credentials file supplies it).
    sync_buf_path:
        Path to persist the getUpdates sync buffer.
    on_response:
        Async callback invoked with each successful getUpdates response.
        The callback is responsible for extracting messages and dispatching.
    stop_event:
        When set, the loop exits cleanly.
    """
    await anyio.to_thread.run_sync(
        functools.partial(sync_buf_path.parent.mkdir, parents=True, exist_ok=True)
    )
    sync_buf: str = (
        await anyio.to_thread.run_sync(functools.partial(load_get_updates_buf, sync_buf_path)) or ""
    )
    logger.info("[%s] Poll loop started, sync_buf restored (%d bytes)", account_id, len(sync_buf))

    consecutive_failures = 0
    while not stop_event.is_set():
        try:
            if is_session_paused(account_id):
                remaining_ms = get_remaining_pause_ms(account_id)
                logger.warning(
                    "[%s] Session paused, %d min remaining",
                    account_id,
                    remaining_ms // 60_000,
                )
                await anyio.sleep(SESSION_PAUSE_POLL_DELAY)
                continue

            resp = await get_updates(
                base_url=base_url,
                token=token,
                get_updates_buf=sync_buf,
            )

            is_api_error = (resp.ret is not None and resp.ret != 0) or (
                resp.errcode is not None and resp.errcode != 0
            )
            if is_api_error:
                is_expired = (
                    resp.errcode == SESSION_EXPIRED_ERRCODE or resp.ret == SESSION_EXPIRED_ERRCODE
                )
                if is_expired:
                    pause_session(account_id)
                    logger.error(
                        "[%s] Session expired (errcode=%d), pausing",
                        account_id,
                        SESSION_EXPIRED_ERRCODE,
                    )
                    consecutive_failures = 0
                    continue

                consecutive_failures += 1
                logger.warning(
                    "[%s] API error: ret=%s errcode=%s (%d/%d)",
                    account_id,
                    resp.ret,
                    resp.errcode,
                    consecutive_failures,
                    MAX_CONSECUTIVE_FAILURES,
                )
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    consecutive_failures = 0
                    await anyio.sleep(FAILURE_BACKOFF_DELAY)
                else:
                    await anyio.sleep(FAILURE_RETRY_DELAY)
                continue

            consecutive_failures = 0

            new_buf = resp.get_updates_buf
            if new_buf and new_buf != sync_buf:
                sync_buf = new_buf
                await anyio.to_thread.run_sync(
                    functools.partial(save_get_updates_buf, sync_buf_path, new_buf)
                )

            await on_response(resp)

        except Exception:
            if stop_event.is_set():
                logger.info("[%s] Poll loop stopped (cancelled)", account_id)
                return
            consecutive_failures += 1
            logger.exception(
                "[%s] Poll failure #%d/%d",
                account_id,
                consecutive_failures,
                MAX_CONSECUTIVE_FAILURES,
            )
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                consecutive_failures = 0
                await anyio.sleep(FAILURE_BACKOFF_DELAY)
            else:
                await anyio.sleep(FAILURE_RETRY_DELAY)

    logger.info("[%s] Poll loop ended", account_id)
