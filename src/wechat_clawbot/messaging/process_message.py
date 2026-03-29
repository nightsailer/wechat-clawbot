"""Message processing pipeline: route -> download media -> dispatch reply.

This module mirrors the TS ``process-message.ts`` but replaces framework-specific
callbacks (routing, session, reply dispatch) with a ``ProcessMessageDeps`` protocol
that the host application must supply.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from wechat_clawbot.api.client import WeixinApiOptions
from wechat_clawbot.api.types import MessageItem, MessageItemType, WeixinMessage
from wechat_clawbot.media.download import InboundMediaOpts, SaveMediaFn, download_media_from_item
from wechat_clawbot.messaging.debug_mode import is_debug_mode
from wechat_clawbot.messaging.error_notice import send_weixin_error_notice
from wechat_clawbot.messaging.inbound import (
    is_media_item,
    set_context_token,
    weixin_message_to_msg_context,
)
from wechat_clawbot.messaging.send import send_message_weixin
from wechat_clawbot.messaging.slash_commands import SlashCommandContext, handle_slash_command
from wechat_clawbot.util.logger import logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


class ReplyDispatcher(Protocol):
    """Protocol for the framework's reply dispatch mechanism."""

    async def dispatch(self, text: str, media_url: str | None = None) -> None: ...


@dataclass
class ProcessMessageDeps:
    """Dependencies injected by the monitor loop / host application."""

    account_id: str
    config: dict[str, Any]
    base_url: str
    cdn_base_url: str
    token: str | None = None
    typing_ticket: str | None = None
    log: Callable[[str], None] = lambda msg: None
    err_log: Callable[[str], None] = lambda msg: None
    save_media: SaveMediaFn | None = None
    dispatch_reply: Callable[..., Awaitable[None]] | None = None


def _extract_text_body(item_list: list[MessageItem] | None) -> str:
    if not item_list:
        return ""
    for item in item_list:
        if item.type == MessageItemType.TEXT and item.text_item and item.text_item.text is not None:
            return str(item.text_item.text)
    return ""


async def process_one_message(
    full: WeixinMessage,
    deps: ProcessMessageDeps,
) -> None:
    """Process a single inbound message: slash commands -> download media -> convert -> dispatch."""
    received_at = time.time() * 1000
    debug = is_debug_mode(deps.account_id)

    text_body = _extract_text_body(full.item_list)

    # Slash command handling
    if text_body.startswith("/"):
        slash_result = await handle_slash_command(
            text_body,
            SlashCommandContext(
                to=full.from_user_id or "",
                context_token=full.context_token,
                base_url=deps.base_url,
                token=deps.token,
                account_id=deps.account_id,
                log=deps.log,
                err_log=deps.err_log,
            ),
            received_at,
            full.create_time_ms,
        )
        if slash_result.handled:
            logger.info("[weixin] Slash command handled, skipping AI pipeline")
            return

    # Media download
    media_opts = InboundMediaOpts()

    main_media = _find_main_media_item(full.item_list)
    ref_media = _find_ref_media_item(full.item_list) if not main_media else None
    media_item = main_media or ref_media

    media_download_ms = 0
    if media_item and deps.save_media:
        start = time.time() * 1000
        downloaded = await download_media_from_item(
            media_item,
            cdn_base_url=deps.cdn_base_url,
            save_media=deps.save_media,
            log=deps.log,
            err_log=deps.err_log,
            label="ref" if ref_media else "inbound",
        )
        media_opts = downloaded
        media_download_ms = int(time.time() * 1000 - start)

    # Convert to MsgContext
    ctx = weixin_message_to_msg_context(full, deps.account_id, media_opts)

    # Cache context token
    context_token = ctx.context_token
    if context_token:
        set_context_token(deps.account_id, full.from_user_id or "", context_token)

    # Dispatch reply (if framework callback is provided)
    if deps.dispatch_reply:
        try:
            await deps.dispatch_reply(ctx)
        except Exception as e:
            logger.error(f"dispatchReply: error err={e}")
            if context_token:
                await send_weixin_error_notice(
                    to=ctx.to,
                    context_token=context_token,
                    message=f"⚠️ 消息处理失败：{str(e)[:200]}",
                    base_url=deps.base_url,
                    token=deps.token,
                    err_log=deps.err_log,
                )

    # Debug timing
    if debug and context_token:
        dispatch_done = time.time() * 1000
        event_ts = full.create_time_ms or 0
        total = (
            f"{int(dispatch_done - event_ts)}ms"
            if event_ts > 0
            else f"{int(dispatch_done - received_at)}ms"
        )
        timing_text = (
            f"⏱ Debug 全链路\n"
            f"├ mediaDownload: {media_download_ms}ms\n"
            f"├ 总耗时: {total}\n"
            f"└ eventTime: {event_ts}"
        )
        try:
            await send_message_weixin(
                to=ctx.to,
                text=timing_text,
                opts=WeixinApiOptions(
                    base_url=deps.base_url, token=deps.token, context_token=context_token
                ),
            )
        except Exception as e:
            logger.error(f"debug-timing: send FAILED err={e}")


def _wrapper_has_downloadable_media(media_obj: Any) -> bool:
    """Check if a media wrapper (image_item, video_item, etc.) has downloadable media."""
    m = getattr(media_obj, "media", None) if media_obj else None
    return m is not None and m.has_download_source


def _find_main_media_item(item_list: list[MessageItem] | None) -> MessageItem | None:
    """Find the first downloadable media item (priority: IMAGE > VIDEO > FILE > VOICE)."""
    if not item_list:
        return None
    for type_ in (MessageItemType.IMAGE, MessageItemType.VIDEO, MessageItemType.FILE):
        for item in item_list:
            if item.type == type_:
                media_obj = getattr(
                    item,
                    {
                        MessageItemType.IMAGE: "image_item",
                        MessageItemType.VIDEO: "video_item",
                        MessageItemType.FILE: "file_item",
                    }[type_],
                    None,
                )
                if _wrapper_has_downloadable_media(media_obj):
                    return item
    # Voice: only if no text transcription
    for item in item_list:
        if (
            item.type == MessageItemType.VOICE
            and item.voice_item
            and _wrapper_has_downloadable_media(item.voice_item)
            and not item.voice_item.text
        ):
            return item
    return None


def _find_ref_media_item(item_list: list[MessageItem] | None) -> MessageItem | None:
    """Find a media item referenced via a quoted message."""
    if not item_list:
        return None
    for item in item_list:
        if (
            item.type == MessageItemType.TEXT
            and item.ref_msg
            and item.ref_msg.message_item
            and is_media_item(item.ref_msg.message_item)
        ):
            return item.ref_msg.message_item
    return None
