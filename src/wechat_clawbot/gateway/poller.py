"""Poller module — manages getUpdates long-poll loop for a WeChat Bot account."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import anyio

if TYPE_CHECKING:
    from pathlib import Path

    from wechat_clawbot.api.types import GetUpdatesResp

from wechat_clawbot.api.poll_core import poll_loop
from wechat_clawbot.api.types import MessageType
from wechat_clawbot.messaging.inbound import body_from_item_list

from .types import InboundMessage

logger = logging.getLogger(__name__)

# Callback type for inbound messages
MessageCallback = Callable[[InboundMessage], Awaitable[None]]

# Re-export for convenience
__all__ = ["MessageCallback", "Poller", "PollerManager"]


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
        self._stop_event: anyio.Event | None = None

    @property
    def _sync_buf_path(self) -> Path:
        return self._state_dir / "accounts" / f"{self.account_id}.sync.json"

    async def run(self, stop_event: anyio.Event) -> None:
        """Run the poll loop until *stop_event* is set."""
        self._stop_event = stop_event

        async def _process_response(resp: GetUpdatesResp) -> None:
            for msg in resp.msgs or []:
                if msg.message_type != MessageType.USER:
                    continue

                sender_id = msg.from_user_id or ""
                text = body_from_item_list(msg.item_list)
                context_token = msg.context_token

                inbound = InboundMessage(
                    account_id=self.account_id,
                    sender_id=sender_id,
                    text=text,
                    context_token=context_token,
                    message_id=str(msg.message_id) if msg.message_id is not None else "",
                    timestamp=msg.create_time_ms / 1000.0 if msg.create_time_ms else time.time(),
                )

                try:
                    await self._on_message(inbound)
                except Exception:
                    logger.exception(
                        "[%s] Error in on_message callback for message %s",
                        self.account_id,
                        inbound.message_id,
                    )

        await poll_loop(
            account_id=self.account_id,
            base_url=self._base_url,
            token=self._token,
            sync_buf_path=self._sync_buf_path,
            on_response=_process_response,
            stop_event=stop_event,
        )

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
