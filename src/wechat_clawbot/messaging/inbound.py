"""Inbound message conversion: WeixinMessage -> WeixinMsgContext."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from wechat_clawbot.api.types import MessageItem, MessageItemType, WeixinMessage
from wechat_clawbot.util.logger import logger
from wechat_clawbot.util.random import generate_id

if TYPE_CHECKING:
    from wechat_clawbot.media.download import InboundMediaOpts

# ---------------------------------------------------------------------------
# Context token store (in-process LRU cache: accountId+userId -> contextToken)
# ---------------------------------------------------------------------------

_CONTEXT_TOKEN_MAX_ENTRIES = 10_000

# OrderedDict provides O(1) move_to_end for LRU eviction.
_context_token_store: OrderedDict[str, str] = OrderedDict()


def _context_token_key(account_id: str, user_id: str) -> str:
    return f"{account_id}:{user_id}"


def set_context_token(account_id: str, user_id: str, token: str) -> None:
    """Store a context token for a given account+user pair (LRU-bounded)."""
    k = _context_token_key(account_id, user_id)
    logger.debug(f"setContextToken: key={k}")
    _context_token_store[k] = token
    _context_token_store.move_to_end(k)
    while len(_context_token_store) > _CONTEXT_TOKEN_MAX_ENTRIES:
        _context_token_store.popitem(last=False)


def get_context_token(account_id: str, user_id: str) -> str | None:
    """Retrieve the cached context token for a given account+user pair."""
    k = _context_token_key(account_id, user_id)
    val = _context_token_store.get(k)
    logger.debug(
        f"getContextToken: key={k} found={val is not None} storeSize={len(_context_token_store)}"
    )
    return val


# ---------------------------------------------------------------------------
# MsgContext
# ---------------------------------------------------------------------------


@dataclass
class WeixinMsgContext:
    """Inbound context passed to the core pipeline (matches MsgContext shape)."""

    body: str = ""
    from_user: str = ""
    to: str = ""
    account_id: str = ""
    originating_channel: str = "openclaw-weixin"
    originating_to: str = ""
    message_sid: str = ""
    timestamp: int | None = None
    provider: str = "openclaw-weixin"
    chat_type: str = "direct"
    session_key: str | None = None
    context_token: str | None = None
    media_url: str | None = None
    media_path: str | None = None
    media_type: str | None = None
    command_body: str | None = None
    command_authorized: bool | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def is_media_item(item: MessageItem) -> bool:
    """Return ``True`` if the item is a media type (image, video, file, or voice)."""
    return item.type in (
        MessageItemType.IMAGE,
        MessageItemType.VIDEO,
        MessageItemType.FILE,
        MessageItemType.VOICE,
    )


def body_from_item_list(item_list: list[MessageItem] | None) -> str:
    if not item_list:
        return ""
    for item in item_list:
        if item.type == MessageItemType.TEXT and item.text_item and item.text_item.text is not None:
            text = str(item.text_item.text)
            ref = item.ref_msg
            if not ref:
                return text
            if ref.message_item and is_media_item(ref.message_item):
                return text
            parts: list[str] = []
            if ref.title:
                parts.append(ref.title)
            if ref.message_item:
                ref_body = body_from_item_list([ref.message_item])
                if ref_body:
                    parts.append(ref_body)
            if not parts:
                return text
            return f"[引用: {' | '.join(parts)}]\n{text}"
        if item.type == MessageItemType.VOICE and item.voice_item and item.voice_item.text:
            return item.voice_item.text
    return ""


def weixin_message_to_msg_context(
    msg: WeixinMessage,
    account_id: str,
    opts: InboundMediaOpts | None = None,
) -> WeixinMsgContext:
    """Convert a :class:`WeixinMessage` to a :class:`WeixinMsgContext`."""

    from_user_id = msg.from_user_id or ""
    ctx = WeixinMsgContext(
        body=body_from_item_list(msg.item_list),
        from_user=from_user_id,
        to=from_user_id,
        account_id=account_id,
        originating_to=from_user_id,
        message_sid=generate_id("openclaw-weixin"),
        timestamp=msg.create_time_ms,
    )
    if msg.context_token:
        ctx.context_token = msg.context_token

    if opts:
        if opts.decrypted_pic_path:
            ctx.media_path = opts.decrypted_pic_path
            ctx.media_type = "image/*"
        elif opts.decrypted_video_path:
            ctx.media_path = opts.decrypted_video_path
            ctx.media_type = "video/mp4"
        elif opts.decrypted_file_path:
            ctx.media_path = opts.decrypted_file_path
            ctx.media_type = opts.file_media_type or "application/octet-stream"
        elif opts.decrypted_voice_path:
            ctx.media_path = opts.decrypted_voice_path
            ctx.media_type = opts.voice_media_type or "audio/wav"

    return ctx
