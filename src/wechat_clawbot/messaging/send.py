"""Send text and media messages downstream to Weixin."""

from __future__ import annotations

import base64
import re
from typing import TYPE_CHECKING

from wechat_clawbot.api.client import WeixinApiOptions, send_message
from wechat_clawbot.api.types import (
    CDNMedia,
    FileItem,
    ImageItem,
    MessageItem,
    MessageItemType,
    MessageState,
    MessageType,
    SendMessageReq,
    TextItem,
    VideoItem,
    WeixinMessage,
)
from wechat_clawbot.util.logger import logger
from wechat_clawbot.util.random import generate_id

if TYPE_CHECKING:
    from wechat_clawbot.cdn.upload import UploadedFileInfo


def _generate_client_id() -> str:
    return generate_id("openclaw-weixin")


def _warn_missing_context_token(opts: WeixinApiOptions, caller: str) -> None:
    """Log warning if ``context_token`` is absent; no longer blocks sending.

    Since openclaw-weixin 2.1.1, contextToken is optional for bot-initiated
    messages — the server will use the last active session for the recipient.
    Missing contextToken may cause the message to not associate with the
    correct conversation, but it will still be delivered.
    """
    if not opts.context_token:
        logger.warning(f"{caller}: contextToken missing for to, sending without context")


def _build_upload_cdn_media(uploaded: UploadedFileInfo) -> CDNMedia:
    """Build a :class:`CDNMedia` from upload results (shared by image/video/file senders)."""
    return CDNMedia(
        encrypt_query_param=uploaded.download_encrypted_query_param,
        aes_key=base64.b64encode(uploaded.aeskey.encode()).decode(),
        encrypt_type=1,
    )


def markdown_to_plain_text(text: str) -> str:
    """Convert markdown-formatted model reply to plain text for Weixin delivery."""
    result = text
    # Code blocks: strip fences, keep code content
    result = re.sub(r"```[^\n]*\n?([\s\S]*?)```", lambda m: m.group(1).strip(), result)
    # Images: remove entirely
    result = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", result)
    # Links: keep display text only
    result = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", result)
    # Tables: remove separator rows
    result = re.sub(r"^\|[\s:|-]+\|$", "", result, flags=re.MULTILINE)
    # Tables: strip pipes and convert to spaces
    result = re.sub(
        r"^\|(.+)\|$",
        lambda m: "  ".join(cell.strip() for cell in m.group(1).split("|")),
        result,
        flags=re.MULTILINE,
    )
    # Strip remaining markdown: bold, italic, strikethrough, headers
    result = re.sub(r"\*\*(.+?)\*\*", r"\1", result)
    result = re.sub(r"\*(.+?)\*", r"\1", result)
    result = re.sub(r"~~(.+?)~~", r"\1", result)
    result = re.sub(r"^#{1,6}\s+", "", result, flags=re.MULTILINE)
    return result


def _build_text_message_req(
    to: str, text: str, context_token: str | None, client_id: str
) -> SendMessageReq:
    item_list: list[MessageItem] | None = None
    if text:
        item_list = [
            MessageItem(
                type=MessageItemType.TEXT,
                text_item=TextItem(text=text),
            )
        ]
    return SendMessageReq(
        msg=WeixinMessage(
            from_user_id="",
            to_user_id=to,
            client_id=client_id,
            message_type=MessageType.BOT,
            message_state=MessageState.FINISH,
            item_list=item_list,
            context_token=context_token or None,
        )
    )


async def send_message_weixin(to: str, text: str, opts: WeixinApiOptions) -> dict[str, str]:
    """Send a plain text message. Returns ``{messageId: ...}``."""
    _warn_missing_context_token(opts, "sendMessageWeixin")
    client_id = _generate_client_id()
    req = _build_text_message_req(to, text, opts.context_token, client_id)
    try:
        await send_message(opts, req)
    except Exception as e:
        logger.error(f"sendMessageWeixin: failed to={to} clientId={client_id} err={e}")
        raise
    return {"messageId": client_id}


async def _send_media_items(
    to: str,
    text: str,
    media_item: MessageItem,
    opts: WeixinApiOptions,
    label: str,
) -> dict[str, str]:
    """Send text + media item as separate requests."""

    items: list[MessageItem] = []
    if text:
        items.append(MessageItem(type=MessageItemType.TEXT, text_item=TextItem(text=text)))
    items.append(media_item)

    last_client_id = ""
    for item in items:
        last_client_id = _generate_client_id()
        req = SendMessageReq(
            msg=WeixinMessage(
                from_user_id="",
                to_user_id=to,
                client_id=last_client_id,
                message_type=MessageType.BOT,
                message_state=MessageState.FINISH,
                item_list=[item],
                context_token=opts.context_token or None,
            )
        )
        try:
            await send_message(opts, req)
        except Exception as e:
            logger.error(f"{label}: failed to={to} clientId={last_client_id} err={e}")
            raise
    return {"messageId": last_client_id}


async def send_image_message_weixin(
    to: str, text: str, uploaded: UploadedFileInfo, opts: WeixinApiOptions
) -> dict[str, str]:
    """Send an image message using a previously uploaded file."""
    _warn_missing_context_token(opts, "sendImageMessageWeixin")
    image_item = MessageItem(
        type=MessageItemType.IMAGE,
        image_item=ImageItem(
            media=_build_upload_cdn_media(uploaded),
            mid_size=uploaded.file_size_ciphertext,
        ),
    )
    return await _send_media_items(to, text, image_item, opts, "sendImageMessageWeixin")


async def send_video_message_weixin(
    to: str, text: str, uploaded: UploadedFileInfo, opts: WeixinApiOptions
) -> dict[str, str]:
    """Send a video message using a previously uploaded file."""
    _warn_missing_context_token(opts, "sendVideoMessageWeixin")
    video_item = MessageItem(
        type=MessageItemType.VIDEO,
        video_item=VideoItem(
            media=_build_upload_cdn_media(uploaded),
            video_size=uploaded.file_size_ciphertext,
        ),
    )
    return await _send_media_items(to, text, video_item, opts, "sendVideoMessageWeixin")


async def send_file_message_weixin(
    to: str, text: str, file_name: str, uploaded: UploadedFileInfo, opts: WeixinApiOptions
) -> dict[str, str]:
    """Send a file attachment using a previously uploaded file."""
    _warn_missing_context_token(opts, "sendFileMessageWeixin")
    file_item = MessageItem(
        type=MessageItemType.FILE,
        file_item=FileItem(
            media=_build_upload_cdn_media(uploaded),
            file_name=file_name,
            len=str(uploaded.file_size),
        ),
    )
    return await _send_media_items(to, text, file_item, opts, "sendFileMessageWeixin")
