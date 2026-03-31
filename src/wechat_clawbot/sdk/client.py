"""ClawBot SDK client — connects to gateway via WebSocket."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from wechat_clawbot.gateway.channels.sdk_channel import (
    MSG_TYPE_MESSAGE,
    MSG_TYPE_PING,
    MSG_TYPE_REPLY,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """An inbound message from a WeChat user."""

    sender_id: str
    text: str
    context_token: str | None = None


class ClawBotClient:
    """SDK client that connects to the gateway WebSocket endpoint."""

    def __init__(
        self,
        gateway_url: str,
        endpoint_id: str,
        token: str = "",
        reconnect: bool = True,
        reconnect_delay: float = 5.0,
    ) -> None:
        self._gateway_url = gateway_url.rstrip("/")
        self._endpoint_id = endpoint_id
        self._token = token
        self._reconnect = reconnect
        self._reconnect_delay = reconnect_delay
        self._ws: Any = None
        self._closed = False

    @property
    def ws_url(self) -> str:
        """Compute the WebSocket URL from the HTTP gateway URL."""
        base = self._gateway_url.replace("http://", "ws://").replace("https://", "wss://")
        return f"{base}/sdk/{self._endpoint_id}/ws"

    async def __aenter__(self) -> ClawBotClient:
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def connect(self) -> None:
        """Connect to the gateway WebSocket."""
        try:
            import websockets  # type: ignore[import-untyped]

            self._ws = await websockets.connect(self.ws_url)
            logger.info("Connected to gateway: %s", self.ws_url)
        except ImportError:
            raise ImportError(
                "websockets package required for SDK client. "
                "Install with: pip install wechat-clawbot[sdk]"
            ) from None

    async def close(self) -> None:
        """Close the connection."""
        self._closed = True
        if self._ws:
            await self._ws.close()

    async def messages(self) -> AsyncIterator[Message]:
        """Iterate over incoming messages from WeChat users."""
        while not self._closed:
            try:
                if not self._ws:
                    await self.connect()

                async for raw in self._ws:
                    data = json.loads(raw)
                    if data.get("type") == MSG_TYPE_MESSAGE:
                        yield Message(
                            sender_id=data.get("sender_id", ""),
                            text=data.get("text", ""),
                            context_token=data.get("context_token"),
                        )
            except Exception:
                if self._closed:
                    break
                logger.exception("WebSocket connection lost")
                if self._reconnect:
                    logger.info("Reconnecting in %.1fs...", self._reconnect_delay)
                    await asyncio.sleep(self._reconnect_delay)
                    self._ws = None
                else:
                    break

    async def reply(self, sender_id: str, text: str) -> None:
        """Send a reply to a WeChat user."""
        if not self._ws:
            raise RuntimeError("Not connected")
        await self._ws.send(
            json.dumps({"type": MSG_TYPE_REPLY, "sender_id": sender_id, "text": text})
        )

    async def ping(self) -> None:
        """Send a ping to keep the connection alive."""
        if self._ws:
            await self._ws.send(json.dumps({"type": MSG_TYPE_PING}))
