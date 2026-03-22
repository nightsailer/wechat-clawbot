"""MCP Channel server — bridges WeChat messages into a Claude Code session.

Flow:
  1. QR login via ilink/bot/get_bot_qrcode + get_qrcode_status
  2. Long-poll ilink/bot/getupdates for incoming WeChat messages
  3. Forward messages to Claude Code as channel notifications
  4. Expose ``wechat_reply`` tool so Claude can send messages back
"""

from __future__ import annotations

import asyncio
import collections
import contextlib
import os
import sys
import tempfile
from typing import TYPE_CHECKING, Any

from mcp import types as mcp_types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.shared.message import SessionMessage
from mcp.types import JSONRPCMessage, JSONRPCNotification

from wechat_clawbot._version import __version__
from wechat_clawbot.api.client import WeixinApiOptions, get_updates, send_message
from wechat_clawbot.api.types import (
    MessageItem,
    MessageItemType,
    MessageState,
    MessageType,
    SendMessageReq,
    TextItem,
    WeixinMessage,
)
from wechat_clawbot.messaging.inbound import body_from_item_list
from wechat_clawbot.util.random import generate_id

if TYPE_CHECKING:
    from pathlib import Path

    from anyio.abc import ObjectSendStream

    from .credentials import AccountData

CHANNEL_NAME = "wechat"
LONG_POLL_TIMEOUT_MS = 35_000
MAX_CONSECUTIVE_FAILURES = 3
BACKOFF_DELAY_MS = 30_000
RETRY_DELAY_MS = 2_000
MAX_CONTEXT_TOKENS = 500


# Logging goes to stderr because stdout is reserved for MCP stdio transport.
def _log(msg: str) -> None:
    print(f"[wechat-channel] {msg}", file=sys.stderr, flush=True)


def _log_error(msg: str) -> None:
    print(f"[wechat-channel] ERROR: {msg}", file=sys.stderr, flush=True)


def _atomic_write_text(path: Path, text: str) -> None:
    """Write *text* to *path* atomically via a temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        os.write(fd, text.encode("utf-8"))
        os.close(fd)
        fd = -1  # mark as closed
        os.replace(tmp, path)
    except BaseException:
        if fd >= 0:
            os.close(fd)
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


class _LRUDict(collections.OrderedDict[str, str]):
    """OrderedDict that evicts the oldest entry when *maxsize* is exceeded."""

    def __init__(self, maxsize: int = MAX_CONTEXT_TOKENS) -> None:
        super().__init__()
        self._maxsize = maxsize

    def __setitem__(self, key: str, value: str) -> None:
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        if len(self) > self._maxsize:
            self.popitem(last=False)


async def _send_text_reply(
    account: AccountData,
    to: str,
    text: str,
    context_token: str,
) -> str:
    """Send a text reply back to a WeChat user. Returns the client_id."""
    client_id = generate_id("claude-code-wechat")
    req = SendMessageReq(
        msg=WeixinMessage(
            from_user_id="",
            to_user_id=to,
            client_id=client_id,
            message_type=MessageType.BOT,
            message_state=MessageState.FINISH,
            item_list=[MessageItem(type=MessageItemType.TEXT, text_item=TextItem(text=text))],
            context_token=context_token,
        )
    )
    await send_message(
        WeixinApiOptions(base_url=account.base_url, token=account.token),
        req,
    )
    return client_id


INSTRUCTIONS = "\n".join(
    [
        'Messages from WeChat users arrive as <channel source="wechat" sender="..." sender_id="...">',
        "Reply using the wechat_reply tool. You MUST pass the sender_id from the inbound tag.",
        "Messages are from real WeChat users via the WeChat ClawBot interface.",
        "Respond naturally in Chinese unless the user writes in another language.",
        "Keep replies concise — WeChat is a chat app, not an essay platform.",
        "Strip markdown formatting (WeChat doesn't render it). Use plain text.",
    ]
)


def create_mcp_server() -> Server:
    """Create and configure the MCP server with channel capabilities."""
    server = Server(
        name=CHANNEL_NAME,
        version=__version__,
        instructions=INSTRUCTIONS,
    )

    @server.list_tools()
    async def list_tools() -> list[mcp_types.Tool]:
        return [
            mcp_types.Tool(
                name="wechat_reply",
                description="Send a text reply back to the WeChat user",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "sender_id": {
                            "type": "string",
                            "description": (
                                "The sender_id from the inbound <channel> tag "
                                "(xxx@im.wechat format)"
                            ),
                        },
                        "text": {
                            "type": "string",
                            "description": "The plain-text message to send (no markdown)",
                        },
                    },
                    "required": ["sender_id", "text"],
                },
            )
        ]

    return server


async def _poll_loop(
    account: AccountData,
    write_stream: ObjectSendStream[SessionMessage],
    context_tokens: _LRUDict,
    ready_event: asyncio.Event,
    stop_event: asyncio.Event,
) -> None:
    """Long-poll getUpdates and push messages to Claude Code as channel notifications.

    Waits for *ready_event* before sending any notifications, ensuring the MCP
    session handshake has completed.
    """
    get_updates_buf = ""

    from .credentials import credentials_dir

    sync_buf_file = credentials_dir() / "sync_buf.txt"
    try:
        get_updates_buf = sync_buf_file.read_text("utf-8")
        _log(f"恢复上次同步状态 ({len(get_updates_buf)} bytes)")
    except (FileNotFoundError, OSError):
        pass

    _log("等待 MCP session 初始化...")
    await ready_event.wait()
    _log("开始监听微信消息...")

    consecutive_failures = 0

    while not stop_event.is_set():
        try:
            resp = await get_updates(
                base_url=account.base_url,
                token=account.token,
                get_updates_buf=get_updates_buf,
                timeout_ms=LONG_POLL_TIMEOUT_MS,
            )

            is_error = (resp.ret is not None and resp.ret != 0) or (
                resp.errcode is not None and resp.errcode != 0
            )
            if is_error:
                consecutive_failures += 1
                _log_error(
                    f"getUpdates 失败: ret={resp.ret} errcode={resp.errcode} "
                    f"errmsg={resp.errmsg or ''} "
                    f"({consecutive_failures}/{MAX_CONSECUTIVE_FAILURES})"
                )
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    consecutive_failures = 0
                    await asyncio.sleep(BACKOFF_DELAY_MS / 1000)
                else:
                    await asyncio.sleep(RETRY_DELAY_MS / 1000)
                continue

            consecutive_failures = 0

            # Persist sync buf — only when actually changed, via non-blocking
            # atomic write to avoid blocking the event loop and partial-write risk.
            new_buf = resp.get_updates_buf
            if new_buf and new_buf != get_updates_buf:
                get_updates_buf = new_buf
                with contextlib.suppress(OSError):
                    await asyncio.to_thread(_atomic_write_text, sync_buf_file, get_updates_buf)

            for msg in resp.msgs or []:
                if msg.message_type != MessageType.USER:
                    continue

                text = body_from_item_list(msg.item_list)
                if not text:
                    continue

                sender_id = msg.from_user_id or "unknown"

                if msg.context_token:
                    context_tokens[sender_id] = msg.context_token

                _log(f"收到消息: from={sender_id} text={text[:50]}...")

                # Use raw write_stream because ServerSession.send_notification
                # requires an active request context that we don't have here.
                try:
                    notification = JSONRPCNotification(
                        method="notifications/claude/channel",
                        params={
                            "content": text,
                            "meta": {
                                "sender": sender_id.split("@")[0] or sender_id,
                                "sender_id": sender_id,
                            },
                        },
                    )
                    await write_stream.send(SessionMessage(message=JSONRPCMessage(notification)))
                except Exception as e:
                    _log_error(f"发送 channel 通知失败: {e}")

        except Exception as e:
            if stop_event.is_set():
                break
            consecutive_failures += 1
            _log_error(f"轮询异常: {e}")
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                consecutive_failures = 0
                await asyncio.sleep(BACKOFF_DELAY_MS / 1000)
            else:
                await asyncio.sleep(RETRY_DELAY_MS / 1000)

    _log("监听已停止")


async def run_channel_server(account: AccountData) -> None:
    """Start the MCP channel server and begin polling for WeChat messages."""
    server = create_mcp_server()
    # LRU-bounded to prevent unbounded memory growth from many distinct senders
    context_tokens: _LRUDict = _LRUDict()

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[mcp_types.TextContent]:
        if name != "wechat_reply":
            raise ValueError(f"unknown tool: {name}")

        args = arguments or {}
        sender_id = args.get("sender_id", "")
        text = args.get("text", "")

        ctx_token = context_tokens.get(sender_id)
        if not ctx_token:
            return [
                mcp_types.TextContent(
                    type="text",
                    text=(
                        f"error: no context_token for {sender_id}. "
                        "The user may need to send a message first."
                    ),
                )
            ]

        try:
            await _send_text_reply(account, sender_id, text, ctx_token)
            return [mcp_types.TextContent(type="text", text="sent")]
        except Exception as e:
            return [mcp_types.TextContent(type="text", text=f"send failed: {e}")]

    stop_event = asyncio.Event()
    ready_event = asyncio.Event()

    async with stdio_server() as (read_stream, write_stream):
        _log("MCP 连接就绪")

        poll_task = asyncio.create_task(
            _poll_loop(account, write_stream, context_tokens, ready_event, stop_event)
        )

        async def _run_with_ready_signal() -> None:
            ready_event.set()
            await server.run(read_stream, write_stream, server.create_initialization_options())

        try:
            await _run_with_ready_signal()
        finally:
            stop_event.set()
            poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await poll_task
