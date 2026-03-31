"""SDK sub-channel — WebSocket endpoint for custom bots using the project SDK."""

from __future__ import annotations

import contextlib
import json
import logging
from typing import TYPE_CHECKING

from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

if TYPE_CHECKING:
    from .base import ConnectCallback, DisconnectCallback, ReplyCallback

logger = logging.getLogger(__name__)

# Shared message type constants (also used by sdk/client.py)
MSG_TYPE_MESSAGE = "message"
MSG_TYPE_REPLY = "reply"
MSG_TYPE_PING = "ping"
MSG_TYPE_PONG = "pong"


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
        # Valid endpoint IDs — set by gateway app; empty means accept any
        self.valid_endpoint_ids: set[str] = set()

    def get_routes(self) -> list[WebSocketRoute]:
        """Return Starlette routes for SDK channel."""
        return [
            WebSocketRoute("/sdk/{endpoint_id}/ws", self._handle_ws),
        ]

    async def _handle_ws(self, ws: WebSocket) -> None:
        endpoint_id = ws.path_params["endpoint_id"]

        # Reject unknown endpoint IDs
        if self.valid_endpoint_ids and endpoint_id not in self.valid_endpoint_ids:
            logger.warning("Rejected SDK connection for unknown endpoint: %s", endpoint_id)
            await ws.close(code=4003, reason="unknown endpoint")
            return

        await ws.accept()
        self._connections[endpoint_id] = ws
        logger.info("SDK client connected: %s", endpoint_id)

        if self._on_connect:
            self._on_connect(endpoint_id)

        try:
            while True:
                raw = await ws.receive_text()
                msg = json.loads(raw)
                msg_type = msg.get("type", "")

                if msg_type == MSG_TYPE_REPLY:
                    sender_id = msg.get("sender_id", "")
                    text = msg.get("text", "")
                    await self._on_reply(endpoint_id, sender_id, text)
                elif msg_type == MSG_TYPE_PING:
                    await ws.send_text(json.dumps({"type": MSG_TYPE_PONG}))
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("SDK channel error for %s", endpoint_id)
        finally:
            self._connections.pop(endpoint_id, None)
            if self._on_disconnect:
                self._on_disconnect(endpoint_id)
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
                        "type": MSG_TYPE_MESSAGE,
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
        return sorted(self._connections)
