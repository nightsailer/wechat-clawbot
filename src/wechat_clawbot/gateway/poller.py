"""Poller module — manages getUpdates long-poll loop for a WeChat Bot account."""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import anyio

if TYPE_CHECKING:
    from pathlib import Path

from wechat_clawbot.api.client import get_updates
from wechat_clawbot.api.session_guard import (
    SESSION_EXPIRED_ERRCODE,
    get_remaining_pause_ms,
    is_session_paused,
    pause_session,
)
from wechat_clawbot.api.types import MessageType
from wechat_clawbot.messaging.inbound import body_from_item_list
from wechat_clawbot.storage.sync_buf import load_get_updates_buf, save_get_updates_buf

from .types import InboundMessage

logger = logging.getLogger(__name__)

# Callback type for inbound messages
MessageCallback = Callable[[InboundMessage], Awaitable[None]]

# Re-export for convenience
__all__ = ["MessageCallback", "Poller", "PollerManager"]

_MAX_CONSECUTIVE_FAILURES = 3
_FAILURE_RETRY_DELAY = 2.0
_FAILURE_BACKOFF_DELAY = 30.0
_SESSION_PAUSE_POLL_DELAY = 60.0


class Poller:
    """Long-poll loop for a single WeChat Bot account."""

    def __init__(
        self,
        account_id: str,
        base_url: str,
        token: str | None,
        on_message: MessageCallback,
        state_dir: Path,
    ) -> None:
        self.account_id = account_id
        self._base_url = base_url
        self._token = token
        self._on_message = on_message
        self._state_dir = state_dir
        self._sync_buf: str = ""
        self._stop_event: anyio.Event | None = None

    @property
    def _sync_buf_path(self) -> Path:
        return self._state_dir / "accounts" / f"{self.account_id}.sync.json"

    async def run(self, stop_event: anyio.Event) -> None:
        """Run the poll loop until *stop_event* is set."""
        self._stop_event = stop_event

        # Restore sync buf from disk
        sync_path = self._sync_buf_path
        await anyio.to_thread.run_sync(
            functools.partial(lambda p: p.parent.mkdir(parents=True, exist_ok=True), sync_path)
        )
        restored = await anyio.to_thread.run_sync(
            functools.partial(load_get_updates_buf, sync_path)
        )
        self._sync_buf = restored or ""
        logger.info(
            "[%s] Poller started, sync_buf restored (%d bytes)",
            self.account_id,
            len(self._sync_buf),
        )

        consecutive_failures = 0
        while not stop_event.is_set():
            try:
                # Check session guard
                if is_session_paused(self.account_id):
                    remaining_ms = get_remaining_pause_ms(self.account_id)
                    logger.warning(
                        "[%s] Session paused, %d min remaining",
                        self.account_id,
                        remaining_ms // 60_000,
                    )
                    await anyio.sleep(_SESSION_PAUSE_POLL_DELAY)
                    continue

                # Long poll
                resp = await get_updates(
                    base_url=self._base_url,
                    token=self._token,
                    get_updates_buf=self._sync_buf,
                )

                # Check for session expiry
                is_api_error = (resp.ret is not None and resp.ret != 0) or (
                    resp.errcode is not None and resp.errcode != 0
                )
                if is_api_error:
                    is_expired = (
                        resp.errcode == SESSION_EXPIRED_ERRCODE
                        or resp.ret == SESSION_EXPIRED_ERRCODE
                    )
                    if is_expired:
                        pause_session(self.account_id)
                        logger.error(
                            "[%s] Session expired (errcode=%d), pausing",
                            self.account_id,
                            SESSION_EXPIRED_ERRCODE,
                        )
                        consecutive_failures = 0
                        continue

                    consecutive_failures += 1
                    logger.warning(
                        "[%s] API error: ret=%s errcode=%s (%d/%d)",
                        self.account_id,
                        resp.ret,
                        resp.errcode,
                        consecutive_failures,
                        _MAX_CONSECUTIVE_FAILURES,
                    )
                    if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                        consecutive_failures = 0
                        await anyio.sleep(_FAILURE_BACKOFF_DELAY)
                    else:
                        await anyio.sleep(_FAILURE_RETRY_DELAY)
                    continue

                consecutive_failures = 0

                # Update sync buf
                new_buf = resp.get_updates_buf
                if new_buf and new_buf != self._sync_buf:
                    self._sync_buf = new_buf
                    await anyio.to_thread.run_sync(
                        functools.partial(save_get_updates_buf, sync_path, new_buf)
                    )

                # Process messages
                for msg in resp.msgs or []:
                    if msg.message_type != MessageType.USER:
                        continue

                    sender_id = msg.from_user_id or ""
                    text = body_from_item_list(msg.item_list)
                    context_token = msg.context_token

                    # context_token caching is handled by app._on_inbound_message

                    inbound = InboundMessage(
                        account_id=self.account_id,
                        sender_id=sender_id,
                        text=text,
                        context_token=context_token,
                        message_id=str(msg.message_id) if msg.message_id is not None else "",
                        timestamp=msg.create_time_ms / 1000.0
                        if msg.create_time_ms
                        else time.time(),
                    )

                    try:
                        await self._on_message(inbound)
                    except Exception:
                        logger.exception(
                            "[%s] Error in on_message callback for message %s",
                            self.account_id,
                            inbound.message_id,
                        )

            except Exception:
                if stop_event.is_set():
                    logger.info("[%s] Poller stopped (cancelled)", self.account_id)
                    return
                consecutive_failures += 1
                logger.exception(
                    "[%s] Poll failure #%d/%d",
                    self.account_id,
                    consecutive_failures,
                    _MAX_CONSECUTIVE_FAILURES,
                )
                if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                    consecutive_failures = 0
                    await anyio.sleep(_FAILURE_BACKOFF_DELAY)
                else:
                    await anyio.sleep(_FAILURE_RETRY_DELAY)

        logger.info("[%s] Poller ended", self.account_id)

    async def stop(self) -> None:
        """Signal the poller to stop."""
        if self._stop_event is not None:
            self._stop_event.set()


class PollerManager:
    """Manages multiple Poller instances, one per Bot account."""

    def __init__(self, state_dir: Path) -> None:
        self._state_dir = state_dir
        self._pollers: dict[str, Poller] = {}

    def add_account(
        self,
        account_id: str,
        base_url: str,
        token: str | None,
        on_message: MessageCallback,
    ) -> None:
        """Register a new account poller."""
        self._pollers[account_id] = Poller(
            account_id=account_id,
            base_url=base_url,
            token=token,
            on_message=on_message,
            state_dir=self._state_dir,
        )

    def remove_account(self, account_id: str) -> Poller | None:
        """Remove an account poller. Returns the removed Poller or None."""
        return self._pollers.pop(account_id, None)

    def get_poller(self, account_id: str) -> Poller | None:
        """Get a poller by account ID."""
        return self._pollers.get(account_id)

    async def start_all(self, stop_event: anyio.Event) -> None:
        """Start all pollers concurrently."""
        if not self._pollers:
            logger.warning("PollerManager: no accounts configured, nothing to poll")
            await stop_event.wait()
            return
        async with anyio.create_task_group() as tg:
            for poller in self._pollers.values():
                tg.start_soon(poller.run, stop_event)

    @property
    def account_ids(self) -> list[str]:
        """Return list of registered account IDs."""
        return list(self._pollers.keys())

    def __len__(self) -> int:
        return len(self._pollers)
