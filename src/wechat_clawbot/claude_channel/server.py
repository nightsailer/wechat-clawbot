"""MCP Channel server — bridges WeChat messages into a Claude Code session.

Flow:
  1. QR login via ilink/bot/get_bot_qrcode + get_qrcode_status
  2. Long-poll ilink/bot/getupdates for incoming WeChat messages
  3. Forward messages to Claude Code as channel notifications
  4. Expose ``wechat_reply`` tool so Claude can send messages back
"""

from __future__ import annotations

import collections
import contextlib
import functools
import os
import sys
import tempfile
from typing import TYPE_CHECKING, Any

import anyio
from mcp import types as mcp_types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.shared.message import SessionMessage
from mcp.types import JSONRPCMessage

from wechat_clawbot._version import __version__
from wechat_clawbot.api.client import (
    WeixinApiOptions,
    get_config,
    get_updates,
    send_message,
    send_typing,
)
from wechat_clawbot.api.types import (
    MessageItem,
    MessageItemType,
    MessageState,
    MessageType,
    SendMessageReq,
    SendTypingReq,
    TextItem,
    TypingStatus,
    WeixinMessage,
)
from wechat_clawbot.auth.accounts import CDN_BASE_URL
from wechat_clawbot.messaging.inbound import (
    body_from_item_list,
    get_restored_tokens_for_server,
    restore_context_tokens,
    set_context_token,
)
from wechat_clawbot.messaging.mcp_defs import INSTRUCTIONS, TOOLS, build_channel_notification
from wechat_clawbot.messaging.send_media import send_weixin_media_file
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
TYPING_KEEPALIVE_INTERVAL = 5  # seconds


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


class _TypingManager:
    """Manages "typing..." indicators with keepalive for active conversations."""

    def __init__(self, opts: WeixinApiOptions) -> None:
        self._opts = opts
        self._typing_tickets: _LRUDict = _LRUDict()
        self._active_scopes: dict[str, anyio.CancelScope] = {}
        self._tg: anyio.abc.TaskGroup | None = None

    def set_task_group(self, tg: anyio.abc.TaskGroup) -> None:
        self._tg = tg

    async def _ensure_typing_ticket(self, sender_id: str, context_token: str | None) -> str | None:
        cached = self._typing_tickets.get(sender_id)
        if cached:
            return cached
        try:
            resp = await get_config(
                self._opts, ilink_user_id=sender_id, context_token=context_token
            )
            if resp.ret == 0 and resp.typing_ticket:
                self._typing_tickets[sender_id] = resp.typing_ticket
                return resp.typing_ticket
        except Exception as e:
            _log_error(f"getConfig 获取 typing_ticket 失败: {e}")
        return None

    async def start(self, sender_id: str, context_token: str | None) -> None:
        """Start typing indicator with periodic keepalive."""
        await self.stop(sender_id)
        ticket = await self._ensure_typing_ticket(sender_id, context_token)
        if not ticket or not self._tg:
            return
        scope = anyio.CancelScope()
        self._active_scopes[sender_id] = scope

        async def _keepalive() -> None:
            with scope:
                while True:
                    try:
                        await send_typing(
                            self._opts,
                            SendTypingReq(
                                ilink_user_id=sender_id,
                                typing_ticket=ticket,
                                status=TypingStatus.TYPING,
                            ),
                        )
                    except Exception as e:
                        _log_error(f"typing keepalive 失败: {e}")
                        return
                    await anyio.sleep(TYPING_KEEPALIVE_INTERVAL)

        self._tg.start_soon(_keepalive)

    async def stop(self, sender_id: str) -> None:
        """Cancel typing indicator for *sender_id*."""
        scope = self._active_scopes.pop(sender_id, None)
        if not scope:
            return
        scope.cancel()
        ticket = self._typing_tickets.get(sender_id)
        if ticket:
            with contextlib.suppress(Exception):
                await send_typing(
                    self._opts,
                    SendTypingReq(
                        ilink_user_id=sender_id,
                        typing_ticket=ticket,
                        status=TypingStatus.CANCEL,
                    ),
                )


async def _send_text_reply(
    opts: WeixinApiOptions,
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
    await send_message(opts, req)
    return client_id


def create_mcp_server() -> Server:
    """Create and configure the MCP server with channel capabilities."""
    server = Server(
        name=CHANNEL_NAME,
        version=__version__,
        instructions=INSTRUCTIONS,
    )

    @server.list_tools()
    async def list_tools() -> list[mcp_types.Tool]:
        return TOOLS

    return server


async def _poll_loop(
    account: AccountData,
    write_stream: ObjectSendStream[SessionMessage],
    context_tokens: _LRUDict,
    typing_mgr: _TypingManager,
    ready_event: anyio.Event,
    stop_event: anyio.Event,
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

    async def _backoff_sleep() -> None:
        """Sleep with exponential back-off; resets counter after reaching the threshold."""
        nonlocal consecutive_failures
        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            consecutive_failures = 0
            await anyio.sleep(BACKOFF_DELAY_MS / 1000)
        else:
            await anyio.sleep(RETRY_DELAY_MS / 1000)

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
                await _backoff_sleep()
                continue

            consecutive_failures = 0

            # Persist sync buf — only when actually changed, via non-blocking
            # atomic write to avoid blocking the event loop and partial-write risk.
            new_buf = resp.get_updates_buf
            if new_buf and new_buf != get_updates_buf:
                get_updates_buf = new_buf
                with contextlib.suppress(OSError):
                    await anyio.to_thread.run_sync(
                        functools.partial(_atomic_write_text, sync_buf_file, get_updates_buf)
                    )

            for msg in resp.msgs or []:
                if msg.message_type != MessageType.USER:
                    continue

                text = body_from_item_list(msg.item_list)
                if not text:
                    continue

                sender_id = msg.from_user_id or "unknown"

                if msg.context_token:
                    context_tokens[sender_id] = msg.context_token
                    set_context_token(account.account_id, sender_id, msg.context_token)

                _log(f"收到消息: from={sender_id} text={text[:50]}...")

                try:
                    notification = build_channel_notification(sender_id, text)
                    await write_stream.send(SessionMessage(message=JSONRPCMessage(notification)))
                except Exception as e:
                    _log_error(f"发送 channel 通知失败: {e}")

        except Exception as e:
            if stop_event.is_set():
                break
            consecutive_failures += 1
            _log_error(f"轮询异常: {e}")
            await _backoff_sleep()

    _log("监听已停止")


async def run_channel_server(account: AccountData) -> None:
    """Start the MCP channel server and begin polling for WeChat messages."""
    server = create_mcp_server()
    # LRU-bounded to prevent unbounded memory growth from many distinct senders
    context_tokens: _LRUDict = _LRUDict()
    api_opts = WeixinApiOptions(base_url=account.base_url, token=account.token)

    # Restore persisted context tokens from disk to survive restarts.
    if account.account_id:
        restore_context_tokens(account.account_id)
        restored = get_restored_tokens_for_server(account.account_id)
        for user_id, token in restored.items():
            context_tokens[user_id] = token
        if restored:
            _log(f"已恢复 {len(restored)} 个 context token（重启不丢会话）")
    typing_mgr = _TypingManager(api_opts)

    def _require_context_token(
        sender_id: str,
    ) -> str | list[mcp_types.TextContent]:
        """Look up context_token for *sender_id*. Returns token or error response."""
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
        return ctx_token

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[mcp_types.TextContent]:
        args = arguments or {}
        sender_id = args.get("sender_id", "")

        if name == "wechat_reply":
            text = args.get("text", "")
            result = _require_context_token(sender_id)
            if isinstance(result, list):
                return result
            await typing_mgr.stop(sender_id)
            try:
                await _send_text_reply(api_opts, sender_id, text, result)
                return [mcp_types.TextContent(type="text", text="sent")]
            except Exception as e:
                return [mcp_types.TextContent(type="text", text=f"send failed: {e}")]

        if name == "wechat_send_file":
            file_path = args.get("file_path", "")
            text = args.get("text", "")
            if not file_path:
                return [mcp_types.TextContent(type="text", text="error: file_path is required")]
            result = _require_context_token(sender_id)
            if isinstance(result, list):
                return result
            await typing_mgr.stop(sender_id)
            try:
                send_opts = WeixinApiOptions(
                    base_url=api_opts.base_url, token=api_opts.token, context_token=result
                )
                await send_weixin_media_file(file_path, sender_id, text, send_opts, CDN_BASE_URL)
                return [mcp_types.TextContent(type="text", text="sent")]
            except Exception as e:
                return [mcp_types.TextContent(type="text", text=f"send failed: {e}")]

        if name == "wechat_typing":
            ctx_token = context_tokens.get(sender_id)
            try:
                await typing_mgr.start(sender_id, ctx_token)
                return [mcp_types.TextContent(type="text", text="typing")]
            except Exception as e:
                return [mcp_types.TextContent(type="text", text=f"typing failed: {e}")]

        raise ValueError(f"unknown tool: {name}")

    stop_event = anyio.Event()
    ready_event = anyio.Event()

    async with stdio_server() as (read_stream, write_stream):
        _log("MCP 连接就绪")

        async with anyio.create_task_group() as tg:
            typing_mgr.set_task_group(tg)

            async def _run_poll() -> None:
                try:
                    await _poll_loop(
                        account,
                        write_stream,
                        context_tokens,
                        typing_mgr,
                        ready_event,
                        stop_event,
                    )
                except Exception as e:
                    _log_error(f"poll_loop 异常退出: {e}")

            tg.start_soon(_run_poll)

            try:
                ready_event.set()
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
