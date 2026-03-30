"""SDK sub-channel — WebSocket endpoint for custom bots using the project SDK."""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import Awaitable, Callable

from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

ReplyCallback = Callable[[str, str, str], Awaitable[None]]  # endpoint_id, sender_id, text
ConnectCallback = Callable[[str], Awaitable[None]]  # endpoint_id
DisconnectCallback = Callable[[str], Awaitable[None]]  # endpoint_id


class SDKChannel:
    """SDK sub-channel using WebSocket transport.

    Exposes a WebSocket endpoint that SDK clients connect to:
        WS /sdk/{endpoint_id}/ws

    Implements the :class:`~wechat_clawbot.gateway.channels.base.SubChannel`
    protocol.
    """

    def __init__(
        self,
        on_reply: ReplyCallback,
        on_connect: ConnectCallback | None = None,
        on_disconnect: DisconnectCallback | None = None,
    ) -> None:
        self._on_reply = on_reply
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect
        self._connections: dict[str, WebSocket] = {}  # endpoint_id -> ws

    def get_routes(self) -> list[WebSocketRoute]:
        """Return Starlette routes for SDK channel."""
        return [
            WebSocketRoute("/sdk/{endpoint_id}/ws", self._handle_ws),
        ]

    async def _handle_ws(self, ws: WebSocket) -> None:
        endpoint_id = ws.path_params["endpoint_id"]
        await ws.accept()
        self._connections[endpoint_id] = ws
        logger.info("SDK client connected: %s", endpoint_id)

        if self._on_connect:
            await self._on_connect(endpoint_id)

        try:
            while True:
                raw = await ws.receive_text()
                msg = json.loads(raw)
                msg_type = msg.get("type", "")

                if msg_type == "reply":
                    sender_id = msg.get("sender_id", "")
                    text = msg.get("text", "")
                    await self._on_reply(endpoint_id, sender_id, text)
                elif msg_type == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("SDK channel error for %s", endpoint_id)
        finally:
            self._connections.pop(endpoint_id, None)
            if self._on_disconnect:
                await self._on_disconnect(endpoint_id)
            logger.info("SDK client disconnected: %s", endpoint_id)

    # ---- SubChannel interface -----------------------------------------------

    async def start(self) -> None:
        """Start is a no-op; the ASGI server is managed externally."""

    async def stop(self) -> None:
        """Close all active WebSocket connections."""
        for ws in list(self._connections.values()):
            with contextlib.suppress(Exception):
                await ws.close()
        self._connections.clear()

    async def deliver_message(
        self,
        endpoint_id: str,
        sender_id: str,
        text: str,
        context_token: str | None = None,
        media_path: str = "",
        media_type: str = "",
    ) -> bool:
        """Deliver a message to a connected SDK endpoint.

        Returns ``True`` on success, ``False`` if the endpoint is not connected.
        """
        ws = self._connections.get(endpoint_id)
        if not ws:
            return False
        try:
            await ws.send_text(
                json.dumps(
                    {
                        "type": "message",
                        "sender_id": sender_id,
                        "text": text,
                        "context_token": context_token,
                    }
                )
            )
            return True
        except Exception:
            logger.exception("Failed to deliver to SDK endpoint %s", endpoint_id)
            return False

    async def send_reply(
        self,
        endpoint_id: str,
        sender_id: str,
        text: str,
        context_token: str | None = None,
    ) -> None:
        """Replies go through the callback, not back through the channel."""

    def is_endpoint_connected(self, endpoint_id: str) -> bool:
        """Check if a specific endpoint is currently connected."""
        return endpoint_id in self._connections

    def get_connected_endpoints(self) -> list[str]:
        """Return list of currently connected endpoint IDs."""
        return sorted(self._connections.keys())
