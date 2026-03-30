"""MCP sub-channel -- exposes per-endpoint SSE transports for MCP clients.

Each upstream endpoint (e.g. a Claude Code instance) connects via:
    GET  /mcp/{endpoint_id}/sse        -- establish SSE stream
    POST /mcp/{endpoint_id}/messages   -- JSON-RPC messages from client

When the gateway receives a WeChat message routed to an endpoint the
``deliver_message`` method pushes a ``notifications/claude/channel``
notification over the SSE stream -- identical to the format used by
:mod:`wechat_clawbot.claude_channel.server`.

The MCP server registers three tools (``wechat_reply``,
``wechat_send_file``, ``wechat_typing``) that delegate back to the
gateway via callbacks.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import anyio
from mcp.server import Server as MCPServer
from mcp.server.sse import SseServerTransport
from mcp.shared.message import SessionMessage
from mcp.types import JSONRPCMessage, TextContent
from mcp.types import Tool as MCPTool
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from wechat_clawbot.messaging.mcp_defs import INSTRUCTIONS, TOOLS, build_channel_notification

if TYPE_CHECKING:
    from anyio.abc import ObjectSendStream
    from starlette.requests import Request

    from ..channels.base import (
        ConnectCallback,
        DisconnectCallback,
        ReplyCallback,
        SendFileCallback,
        TypingCallback,
    )

logger = logging.getLogger(__name__)


class MCPChannel:
    """MCP sub-channel using SSE transport.

    Exposes SSE endpoints that MCP clients (e.g. Claude Code) connect to.
    Each connected client is associated with one *endpoint_id*.

    Implements the :class:`~wechat_clawbot.gateway.channels.base.SubChannel`
    protocol.
    """

    def __init__(
        self,
        on_reply: ReplyCallback,
        on_send_file: SendFileCallback | None = None,
        on_typing: TypingCallback | None = None,
        on_connect: ConnectCallback | None = None,
        on_disconnect: DisconnectCallback | None = None,
    ) -> None:
        self._on_reply = on_reply
        self._on_send_file = on_send_file
        self._on_typing = on_typing
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect

        # endpoint_id -> write_stream for pushing notifications
        self._write_streams: dict[str, ObjectSendStream[SessionMessage]] = {}
        # endpoint_id -> SseServerTransport (needed for POST handling)
        self._transports: dict[str, SseServerTransport] = {}
        self._app: Starlette | None = None

    # ---- ASGI app -----------------------------------------------------------

    def get_asgi_app(self) -> Starlette:
        """Return the Starlette ASGI app with MCP SSE routes."""
        if self._app is None:
            self._app = Starlette(
                routes=[
                    Route(
                        "/mcp/{endpoint_id}/sse",
                        self._handle_sse,
                        methods=["GET"],
                    ),
                    Route(
                        "/mcp/{endpoint_id}/messages",
                        self._handle_messages,
                        methods=["POST"],
                    ),
                    Route("/health", self._handle_health, methods=["GET"]),
                ],
            )
        return self._app

    # ---- MCP server factory -------------------------------------------------

    def _create_mcp_server(self, endpoint_id: str) -> MCPServer:
        """Create an MCP server instance with tools wired to *endpoint_id*."""
        server = MCPServer(
            name=f"wechat-gateway-{endpoint_id}",
            instructions=INSTRUCTIONS,
        )

        @server.list_tools()
        async def list_tools() -> list[MCPTool]:
            return TOOLS

        @server.call_tool()
        async def call_tool(
            name: str,
            arguments: dict[str, Any] | None,
        ) -> list[TextContent]:
            args = arguments or {}
            sender_id: str = args.get("sender_id", "")

            if name == "wechat_reply":
                text: str = args.get("text", "")
                await self._on_reply(endpoint_id, sender_id, text)
                return [TextContent(type="text", text="sent")]

            if name == "wechat_send_file":
                file_path: str = args.get("file_path", "")
                text = args.get("text", "")
                if self._on_send_file:
                    await self._on_send_file(endpoint_id, sender_id, file_path, text)
                return [TextContent(type="text", text="sent")]

            if name == "wechat_typing":
                if self._on_typing:
                    await self._on_typing(endpoint_id, sender_id)
                return [TextContent(type="text", text="typing")]

            return [TextContent(type="text", text=f"unknown tool: {name}")]

        return server

    # ---- HTTP handlers ------------------------------------------------------

    async def _handle_sse(self, request: Request) -> None:
        """Handle SSE connection from an MCP client."""
        endpoint_id: str = request.path_params["endpoint_id"]
        logger.info("MCP client connecting for endpoint: %s", endpoint_id)

        transport = SseServerTransport(f"/mcp/{endpoint_id}/messages")
        server = self._create_mcp_server(endpoint_id)
        self._transports[endpoint_id] = transport

        async with transport.connect_sse(request.scope, request.receive, request._send) as (
            read_stream,
            write_stream,
        ):
            self._write_streams[endpoint_id] = write_stream
            logger.info("MCP client connected for endpoint: %s", endpoint_id)
            if self._on_connect:
                self._on_connect(endpoint_id)

            try:
                init_options = server.create_initialization_options(
                    experimental_capabilities={"claude/channel": {}},
                )
                await server.run(read_stream, write_stream, init_options)
            finally:
                self._write_streams.pop(endpoint_id, None)
                self._transports.pop(endpoint_id, None)
                logger.info("MCP client disconnected for endpoint: %s", endpoint_id)
                if self._on_disconnect:
                    self._on_disconnect(endpoint_id)

    async def _handle_messages(self, request: Request) -> None:
        """Handle POST messages from an MCP client."""
        endpoint_id: str = request.path_params["endpoint_id"]
        transport = self._transports.get(endpoint_id)
        if not transport:
            response = JSONResponse({"error": "not connected"}, status_code=404)
            await response(request.scope, request.receive, request._send)
            return
        await transport.handle_post_message(request.scope, request.receive, request._send)

    async def _handle_health(self, request: Request) -> JSONResponse:
        """Health check endpoint."""
        return JSONResponse(
            {
                "status": "ok",
                "connected_endpoints": sorted(self._write_streams),
            }
        )

    # ---- SubChannel interface -----------------------------------------------

    async def start(self) -> None:
        """Start is a no-op; the ASGI server is managed externally."""

    async def stop(self) -> None:
        """Clean up sessions."""
        for endpoint_id, ws in list(self._write_streams.items()):
            try:
                await ws.aclose()
            except Exception:
                logger.debug("Error closing write stream for %s", endpoint_id, exc_info=True)
        self._write_streams.clear()
        self._transports.clear()

    async def deliver_message(
        self,
        endpoint_id: str,
        sender_id: str,
        text: str,
        context_token: str | None = None,
        media_path: str = "",
        media_type: str = "",
    ) -> bool:
        """Deliver a WeChat message to a connected MCP endpoint.

        Sends a ``notifications/claude/channel`` JSON-RPC notification over
        the SSE stream, using the same format as
        :mod:`wechat_clawbot.claude_channel.server`.

        Returns ``True`` on success, ``False`` if the endpoint is not
        connected.
        """
        write_stream = self._write_streams.get(endpoint_id)
        if write_stream is None:
            return False

        notification = build_channel_notification(sender_id, text)

        try:
            await write_stream.send(SessionMessage(message=JSONRPCMessage(notification)))
            return True
        except (anyio.ClosedResourceError, anyio.BrokenResourceError):
            logger.warning(
                "Write stream closed for endpoint %s, marking disconnected",
                endpoint_id,
            )
            self._write_streams.pop(endpoint_id, None)
            return False
        except Exception:
            logger.exception("Failed to deliver message to endpoint %s", endpoint_id)
            return False

    def is_endpoint_connected(self, endpoint_id: str) -> bool:
        """Check if a specific endpoint is currently connected."""
        return endpoint_id in self._write_streams

    def get_connected_endpoints(self) -> list[str]:
        """Return list of currently connected endpoint IDs."""
        return sorted(self._write_streams)
