"""Bridge mode -- connects to a gateway SSE endpoint instead of polling WeChat directly.

Supports both Claude Code (channel notifications) and Codex (resource notifications + get_messages tool).
"""

from __future__ import annotations

import collections
import json
import sys
from typing import Any

import anyio
import httpx
from mcp import types as mcp_types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.shared.message import SessionMessage
from mcp.types import JSONRPCMessage

from wechat_clawbot.messaging.mcp_defs import INSTRUCTIONS, TOOLS, build_channel_notification


def _log(msg: str) -> None:
    print(f"[wechat-bridge] {msg}", file=sys.stderr, flush=True)


def _log_error(msg: str) -> None:
    print(f"[wechat-bridge] ERROR: {msg}", file=sys.stderr, flush=True)


_MAX_PENDING = 100


class _MessageQueue:
    """Bounded queue of pending messages for clients that poll via get_messages."""

    def __init__(self, maxsize: int = _MAX_PENDING) -> None:
        self._queue: collections.deque[dict[str, str]] = collections.deque(maxlen=maxsize)

    def push(self, sender_id: str, text: str) -> None:
        self._queue.append({"sender_id": sender_id, "text": text})

    def drain(self) -> list[dict[str, str]]:
        """Return all pending messages and clear the queue."""
        msgs = list(self._queue)
        self._queue.clear()
        return msgs

    def __len__(self) -> int:
        return len(self._queue)


# -- Tool definition for Codex compatibility ---------------------------------

_GET_MESSAGES_TOOL = mcp_types.Tool(
    name="wechat_get_messages",
    description=(
        "Get pending WeChat messages that have not been processed yet. "
        "Call this to check for new incoming messages from WeChat users. "
        "Returns a list of messages with sender_id and text fields."
    ),
    inputSchema={
        "type": "object",
        "properties": {},
    },
)


def _build_bridge_tools() -> list[mcp_types.Tool]:
    """Extend the shared TOOLS list with bridge-only tools."""
    return [*TOOLS, _GET_MESSAGES_TOOL]


# -- Server factory ----------------------------------------------------------


def _create_bridge_server(
    message_queue: _MessageQueue,
) -> Server:
    """Create an MCP server with WeChat tools + wechat_get_messages."""
    server = Server(
        name="wechat-bridge",
        instructions=INSTRUCTIONS,
    )

    bridge_tools = _build_bridge_tools()

    @server.list_tools()
    async def list_tools() -> list[mcp_types.Tool]:
        return bridge_tools

    @server.list_resources()
    async def list_resources() -> list[mcp_types.Resource]:
        return [
            mcp_types.Resource(
                uri="wechat://messages/pending",
                name="Pending WeChat Messages",
                description=f"Number of unread messages: {len(message_queue)}",
                mimeType="application/json",
            ),
        ]

    @server.read_resource()
    async def read_resource(uri: str) -> str:
        # Compare as str — MCP SDK may pass AnyUrl which != str directly
        if str(uri) == "wechat://messages/pending":
            # Peek only (don't drain) — let wechat_get_messages tool handle drain
            msgs = list(message_queue._queue)
            return json.dumps({"messages": msgs, "count": len(msgs)})
        raise ValueError(f"unknown resource: {uri}")

    return server


# -- SSE listener ------------------------------------------------------------


async def _sse_listener(
    gateway_url: str,
    endpoint_id: str,
    write_stream: anyio.abc.ObjectSendStream[SessionMessage],
    message_queue: _MessageQueue,
    stop_event: anyio.Event,
    api_key: str = "",
) -> None:
    """Connect to gateway SSE endpoint and forward messages."""
    sse_url = f"{gateway_url.rstrip('/')}/mcp/{endpoint_id}/sse"
    _log(f"Connecting to gateway SSE: {sse_url}")

    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    backoff = 1.0
    max_backoff = 60.0

    while not stop_event.is_set():
        try:
            async with (
                httpx.AsyncClient(timeout=None, headers=headers) as client,
                client.stream("GET", sse_url) as resp,
            ):
                if resp.status_code == 401:
                    _log_error("SSE auth failed (401). Check --api-key.")
                    await anyio.sleep(max_backoff)
                    continue
                if resp.status_code != 200:
                    _log_error(f"SSE connection failed: {resp.status_code}")
                    await anyio.sleep(min(backoff, max_backoff))
                    backoff = min(backoff * 2, max_backoff)
                    continue

                backoff = 1.0  # reset on success
                _log("Connected to gateway SSE")

                async for line in resp.aiter_lines():
                    if stop_event.is_set():
                        break

                    if not line.startswith("data: "):
                        continue

                    data = line[6:]
                    if not data:
                        continue

                    try:
                        msg = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    method = msg.get("method", "")
                    params = msg.get("params", {})

                    if method != "notifications/claude/channel":
                        continue

                    content = params.get("content", "")
                    meta = params.get("meta", {})
                    sender_id = meta.get("sender_id", "")

                    if not sender_id or not content:
                        continue

                    # Push to message queue (for Codex)
                    message_queue.push(sender_id, content)

                    # Forward as channel notification (for Claude Code)
                    try:
                        notification = build_channel_notification(sender_id, content)
                        await write_stream.send(SessionMessage(JSONRPCMessage(notification)))
                    except Exception as e:
                        _log_error(f"Failed to forward notification: {e}")

                    # Also send resources/updated for Codex
                    try:
                        resource_notification = mcp_types.JSONRPCNotification(
                            jsonrpc="2.0",
                            method="notifications/resources/updated",
                            params={"uri": "wechat://messages/pending"},
                        )
                        await write_stream.send(
                            SessionMessage(JSONRPCMessage(resource_notification))
                        )
                    except Exception:
                        pass  # Non-critical

        except Exception as e:
            if stop_event.is_set():
                break
            _log_error(f"SSE connection error: {e}, reconnecting in {backoff:.0f}s...")
            await anyio.sleep(min(backoff, max_backoff))
            backoff = min(backoff * 2, max_backoff)


# -- Main entry point --------------------------------------------------------


async def run_bridge_server(gateway_url: str, endpoint_id: str, api_key: str = "") -> None:
    """Start the bridge MCP server connecting to a gateway."""
    message_queue = _MessageQueue()
    server = _create_bridge_server(message_queue)

    # Gateway API URL for forwarding tool calls
    gateway_api_url = f"{gateway_url.rstrip('/')}/mcp/{endpoint_id}/messages"

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[mcp_types.TextContent]:
        args = arguments or {}

        if name == "wechat_get_messages":
            msgs = message_queue.drain()
            if not msgs:
                return [mcp_types.TextContent(type="text", text="No pending messages")]
            lines: list[str] = []
            for m in msgs:
                lines.append(
                    f'<channel source="wechat" sender="{m["sender_id"]}" '
                    f'sender_id="{m["sender_id"]}">'
                )
                lines.append(m["text"])
                lines.append("</channel>")
            return [mcp_types.TextContent(type="text", text="\n".join(lines))]

        # Forward other tools (wechat_reply, wechat_send_file, wechat_typing) to gateway
        fwd_headers: dict[str, str] = {}
        if api_key:
            fwd_headers["Authorization"] = f"Bearer {api_key}"
        try:
            async with httpx.AsyncClient(timeout=30.0, headers=fwd_headers) as client:
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": args},
                }
                resp = await client.post(gateway_api_url, json=payload)
                if resp.status_code == 200:
                    result = resp.json()
                    result_content = result.get("result", {}).get("content", [])
                    if result_content:
                        return [
                            mcp_types.TextContent(
                                type="text", text=result_content[0].get("text", "ok")
                            )
                        ]
                    return [mcp_types.TextContent(type="text", text="sent")]
                return [
                    mcp_types.TextContent(type="text", text=f"gateway error: {resp.status_code}")
                ]
        except Exception as e:
            return [mcp_types.TextContent(type="text", text=f"bridge error: {e}")]

    stop_event = anyio.Event()

    async with stdio_server() as (read_stream, write_stream):
        _log("MCP bridge ready")

        async with anyio.create_task_group() as tg:
            tg.start_soon(
                _sse_listener,
                gateway_url,
                endpoint_id,
                write_stream,
                message_queue,
                stop_event,
                api_key,
            )

            try:
                await server.run(
                    read_stream,
                    write_stream,
                    server.create_initialization_options(
                        experimental_capabilities={"claude/channel": {}},
                    ),
                )
            finally:
                stop_event.set()
                tg.cancel_scope.cancel()
