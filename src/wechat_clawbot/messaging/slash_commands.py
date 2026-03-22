"""Weixin slash command handler (/echo, /toggle-debug)."""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from wechat_clawbot.api.client import WeixinApiOptions
from wechat_clawbot.messaging.debug_mode import toggle_debug_mode
from wechat_clawbot.messaging.send import send_message_weixin
from wechat_clawbot.util.logger import logger

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class SlashCommandResult:
    """``handled=True`` means the message was processed as a command and should not go to AI."""

    handled: bool


@dataclass
class SlashCommandContext:
    to: str
    context_token: str | None
    base_url: str
    token: str | None
    account_id: str
    log: Callable[[str], None]
    err_log: Callable[[str], None]


async def _send_reply(ctx: SlashCommandContext, text: str) -> None:
    await send_message_weixin(
        to=ctx.to,
        text=text,
        opts=WeixinApiOptions(
            base_url=ctx.base_url, token=ctx.token, context_token=ctx.context_token
        ),
    )


async def _handle_echo(
    ctx: SlashCommandContext, args: str, received_at: float, event_timestamp: int | None
) -> None:
    message = args.strip()
    if message:
        await _send_reply(ctx, message)
    event_ts = event_timestamp or 0
    now_ms = int(time.time() * 1000)
    platform_delay = f"{int(received_at - event_ts)}ms" if event_ts > 0 else "N/A"
    timing = "\n".join(
        [
            "⏱ 通道耗时",
            f"├ 事件时间: {datetime.fromtimestamp(event_ts / 1000, tz=timezone.utc).isoformat() if event_ts > 0 else 'N/A'}",
            f"├ 平台→插件: {platform_delay}",
            f"└ 插件处理: {now_ms - int(received_at)}ms",
        ]
    )
    await _send_reply(ctx, timing)


async def handle_slash_command(
    content: str,
    ctx: SlashCommandContext,
    received_at: float,
    event_timestamp: int | None = None,
) -> SlashCommandResult:
    """Try to handle a slash command. Returns ``handled=True`` if processed."""
    trimmed = content.strip()
    if not trimmed.startswith("/"):
        return SlashCommandResult(handled=False)

    space_idx = trimmed.find(" ")
    command = trimmed[:space_idx].lower() if space_idx != -1 else trimmed.lower()
    args = trimmed[space_idx + 1 :] if space_idx != -1 else ""

    logger.info(f"[weixin] Slash command: {command}, args: {args[:50]}")

    try:
        if command == "/echo":
            await _handle_echo(ctx, args, received_at, event_timestamp)
            return SlashCommandResult(handled=True)
        elif command == "/toggle-debug":
            enabled = toggle_debug_mode(ctx.account_id)
            await _send_reply(ctx, "Debug 模式已开启" if enabled else "Debug 模式已关闭")
            return SlashCommandResult(handled=True)
        else:
            return SlashCommandResult(handled=False)
    except Exception as e:
        logger.error(f"[weixin] Slash command error: {e}")
        with contextlib.suppress(Exception):
            await _send_reply(ctx, f"❌ 指令执行失败: {str(e)[:200]}")
        return SlashCommandResult(handled=True)
