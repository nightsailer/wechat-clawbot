"""HTTP sub-channel — webhook and websocket for third-party integrations."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from starlette.responses import JSONResponse
from starlette.routing import Route

logger = logging.getLogger(__name__)

ReplyCallback = Callable[[str, str, str], Awaitable[None]]  # endpoint_id, sender_id, text


class HTTPChannel:
    """HTTP sub-channel supporting webhook mode.

    Endpoints are registered with a target URL and optional API key.
    Messages are delivered by POSTing JSON to the URL; if the response
    includes a ``reply`` or ``text`` field, it is forwarded back via the
    reply callback.

    Also exposes ``POST /http/{endpoint_id}/callback`` for receiving
    asynchronous webhook callbacks from endpoints.

    Implements the :class:`~wechat_clawbot.gateway.channels.base.SubChannel`
    protocol.
    """

    def __init__(self, on_reply: ReplyCallback) -> None:
        self._on_reply = on_reply
        self._endpoints: dict[str, dict[str, str]] = {}  # endpoint_id -> {url, api_key}
        self._client: httpx.AsyncClient | None = None

    def register_endpoint(self, endpoint_id: str, url: str, api_key: str = "") -> None:
        """Register a webhook endpoint with its URL and optional API key."""
        self._endpoints[endpoint_id] = {"url": url, "api_key": api_key}

    def unregister_endpoint(self, endpoint_id: str) -> None:
        """Remove an endpoint from the registry."""
        self._endpoints.pop(endpoint_id, None)

    def get_routes(self) -> list[Route]:
        """Routes for receiving webhook callbacks."""
        return [
            Route(
                "/http/{endpoint_id}/callback",
                self._handle_callback,
                methods=["POST"],
            ),
        ]

    async def _handle_callback(self, request: Any) -> JSONResponse:
        """Handle callback from a webhook endpoint."""
        endpoint_id: str = request.path_params["endpoint_id"]
        body = await request.json()
        sender_id: str = body.get("sender_id", "")
        text: str = body.get("text", "")
        if sender_id and text:
            await self._on_reply(endpoint_id, sender_id, text)
        return JSONResponse({"status": "ok"})

    # ---- SubChannel interface -----------------------------------------------

    async def start(self, client: httpx.AsyncClient | None = None) -> None:
        """Create the shared HTTP client.

        Parameters
        ----------
        client:
            Optional pre-configured client (useful for testing).
        """
        self._client = client or httpx.AsyncClient(timeout=30.0)

    async def stop(self) -> None:
        """Close the shared HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def deliver_message(
        self,
        endpoint_id: str,
        sender_id: str,
        text: str,
        context_token: str | None = None,
        media_path: str = "",
        media_type: str = "",
    ) -> bool:
        """POST message to webhook endpoint URL.

        Returns ``True`` on success, ``False`` if the endpoint is not
        registered or delivery fails.
        """
        ep = self._endpoints.get(endpoint_id)
        if not ep or not ep["url"]:
            return False
        if not self._client:
            return False

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if ep["api_key"]:
            headers["Authorization"] = f"Bearer {ep['api_key']}"

        payload = {
            "sender_id": sender_id,
            "text": text,
            "context_token": context_token,
        }

        try:
            resp = await self._client.post(ep["url"], json=payload, headers=headers)
            if resp.status_code == 200:
                # Check if response contains a reply
                try:
                    data = resp.json()
                    reply_text = data.get("reply", "") or data.get("text", "")
                    if reply_text:
                        await self._on_reply(endpoint_id, sender_id, reply_text)
                except Exception:
                    pass
                return True
            logger.warning("Webhook %s returned %d", endpoint_id, resp.status_code)
            return False
        except Exception:
            logger.exception("Webhook delivery failed for %s", endpoint_id)
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
        """Check if a specific endpoint is currently connected (has a URL)."""
        return endpoint_id in self._endpoints and bool(self._endpoints[endpoint_id].get("url"))

    def get_connected_endpoints(self) -> list[str]:
        """Return list of currently connected endpoint IDs."""
        return sorted(eid for eid, ep in self._endpoints.items() if ep.get("url"))
