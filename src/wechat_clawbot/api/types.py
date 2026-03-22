"""Weixin protocol types (mirrors proto: GetUpdatesReq/Resp, WeixinMessage, SendMessageReq).

API uses JSON over HTTP; bytes fields are base64 strings in JSON.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from enum import IntEnum
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class UploadMediaType(IntEnum):
    IMAGE = 1
    VIDEO = 2
    FILE = 3
    VOICE = 4


class MessageType(IntEnum):
    NONE = 0
    USER = 1
    BOT = 2


class MessageItemType(IntEnum):
    NONE = 0
    TEXT = 1
    IMAGE = 2
    VOICE = 3
    FILE = 4
    VIDEO = 5


class MessageState(IntEnum):
    NEW = 0
    GENERATING = 1
    FINISH = 2


class TypingStatus(IntEnum):
    TYPING = 1
    CANCEL = 2


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class BaseInfo:
    channel_version: str | None = None


@dataclass
class CDNMedia:
    encrypt_query_param: str | None = None
    aes_key: str | None = None
    encrypt_type: int | None = None


@dataclass
class TextItem:
    text: str | None = None


@dataclass
class ImageItem:
    media: CDNMedia | None = None
    thumb_media: CDNMedia | None = None
    aeskey: str | None = None
    url: str | None = None
    mid_size: int | None = None
    thumb_size: int | None = None
    thumb_height: int | None = None
    thumb_width: int | None = None
    hd_size: int | None = None


@dataclass
class VoiceItem:
    media: CDNMedia | None = None
    encode_type: int | None = None
    bits_per_sample: int | None = None
    sample_rate: int | None = None
    playtime: int | None = None
    text: str | None = None


@dataclass
class FileItem:
    media: CDNMedia | None = None
    file_name: str | None = None
    md5: str | None = None
    len: str | None = None


@dataclass
class VideoItem:
    media: CDNMedia | None = None
    video_size: int | None = None
    play_length: int | None = None
    video_md5: str | None = None
    thumb_media: CDNMedia | None = None
    thumb_size: int | None = None
    thumb_height: int | None = None
    thumb_width: int | None = None


@dataclass
class RefMessage:
    message_item: MessageItem | None = None
    title: str | None = None


@dataclass
class MessageItem:
    type: int | None = None
    create_time_ms: int | None = None
    update_time_ms: int | None = None
    is_completed: bool | None = None
    msg_id: str | None = None
    ref_msg: RefMessage | None = None
    text_item: TextItem | None = None
    image_item: ImageItem | None = None
    voice_item: VoiceItem | None = None
    file_item: FileItem | None = None
    video_item: VideoItem | None = None


@dataclass
class WeixinMessage:
    seq: int | None = None
    message_id: int | None = None
    from_user_id: str | None = None
    to_user_id: str | None = None
    client_id: str | None = None
    create_time_ms: int | None = None
    update_time_ms: int | None = None
    delete_time_ms: int | None = None
    session_id: str | None = None
    group_id: str | None = None
    message_type: int | None = None
    message_state: int | None = None
    item_list: list[MessageItem] | None = None
    context_token: str | None = None


# ---------------------------------------------------------------------------
# Request / Response
# ---------------------------------------------------------------------------


@dataclass
class GetUpdatesReq:
    get_updates_buf: str | None = None


@dataclass
class GetUpdatesResp:
    ret: int | None = None
    errcode: int | None = None
    errmsg: str | None = None
    msgs: list[WeixinMessage] | None = None
    get_updates_buf: str | None = None
    longpolling_timeout_ms: int | None = None


@dataclass
class GetUploadUrlReq:
    filekey: str | None = None
    media_type: int | None = None
    to_user_id: str | None = None
    rawsize: int | None = None
    rawfilemd5: str | None = None
    filesize: int | None = None
    thumb_rawsize: int | None = None
    thumb_rawfilemd5: str | None = None
    thumb_filesize: int | None = None
    no_need_thumb: bool | None = None
    aeskey: str | None = None


@dataclass
class GetUploadUrlResp:
    upload_param: str | None = None
    thumb_upload_param: str | None = None


@dataclass
class SendMessageReq:
    msg: WeixinMessage | None = None


@dataclass
class SendTypingReq:
    ilink_user_id: str | None = None
    typing_ticket: str | None = None
    status: int | None = None


@dataclass
class GetConfigResp:
    ret: int | None = None
    errmsg: str | None = None
    typing_ticket: str | None = None


# ---------------------------------------------------------------------------
# JSON serialization helpers
# ---------------------------------------------------------------------------


def _dataclass_to_dict(obj: Any) -> dict[str, Any] | Any:
    """Recursively convert a dataclass to a dict, dropping None values."""
    if not dataclasses.is_dataclass(obj) or isinstance(obj, type):
        return obj
    result: dict[str, Any] = {}
    for f in dataclasses.fields(obj):
        v = getattr(obj, f.name)
        if v is None:
            continue
        if dataclasses.is_dataclass(v) and not isinstance(v, type):
            result[f.name] = _dataclass_to_dict(v)
        elif isinstance(v, list):
            result[f.name] = [_dataclass_to_dict(item) for item in v]
        elif isinstance(v, IntEnum):
            result[f.name] = int(v)
        else:
            result[f.name] = v
    return result


def _dict_to_cdn_media(d: dict | None) -> CDNMedia | None:
    if not d:
        return None
    return CDNMedia(
        encrypt_query_param=d.get("encrypt_query_param"),
        aes_key=d.get("aes_key"),
        encrypt_type=d.get("encrypt_type"),
    )


def _dict_to_ref_message(d: dict | None) -> RefMessage | None:
    if not d:
        return None
    return RefMessage(
        message_item=_dict_to_message_item(d.get("message_item")),
        title=d.get("title"),
    )


def _dict_to_message_item(d: dict | None) -> MessageItem | None:
    if not d:
        return None
    img = d.get("image_item")
    voice = d.get("voice_item")
    file_ = d.get("file_item")
    video = d.get("video_item")
    text = d.get("text_item")
    return MessageItem(
        type=d.get("type"),
        create_time_ms=d.get("create_time_ms"),
        update_time_ms=d.get("update_time_ms"),
        is_completed=d.get("is_completed"),
        msg_id=d.get("msg_id"),
        ref_msg=_dict_to_ref_message(d.get("ref_msg")),
        text_item=TextItem(text=text.get("text")) if text else None,
        image_item=ImageItem(
            media=_dict_to_cdn_media(img.get("media")),
            thumb_media=_dict_to_cdn_media(img.get("thumb_media")),
            aeskey=img.get("aeskey"),
            url=img.get("url"),
            mid_size=img.get("mid_size"),
            thumb_size=img.get("thumb_size"),
            thumb_height=img.get("thumb_height"),
            thumb_width=img.get("thumb_width"),
            hd_size=img.get("hd_size"),
        )
        if img
        else None,
        voice_item=VoiceItem(
            media=_dict_to_cdn_media(voice.get("media")),
            encode_type=voice.get("encode_type"),
            bits_per_sample=voice.get("bits_per_sample"),
            sample_rate=voice.get("sample_rate"),
            playtime=voice.get("playtime"),
            text=voice.get("text"),
        )
        if voice
        else None,
        file_item=FileItem(
            media=_dict_to_cdn_media(file_.get("media")),
            file_name=file_.get("file_name"),
            md5=file_.get("md5"),
            len=file_.get("len"),
        )
        if file_
        else None,
        video_item=VideoItem(
            media=_dict_to_cdn_media(video.get("media")),
            video_size=video.get("video_size"),
            play_length=video.get("play_length"),
            video_md5=video.get("video_md5"),
            thumb_media=_dict_to_cdn_media(video.get("thumb_media")),
            thumb_size=video.get("thumb_size"),
            thumb_height=video.get("thumb_height"),
            thumb_width=video.get("thumb_width"),
        )
        if video
        else None,
    )


def dict_to_weixin_message(d: dict) -> WeixinMessage:
    """Parse a raw JSON dict into a :class:`WeixinMessage`."""
    items_raw = d.get("item_list")
    items = [_dict_to_message_item(i) for i in items_raw] if items_raw else None
    # Filter out None items produced by malformed data
    if items:
        items = [i for i in items if i is not None]
    return WeixinMessage(
        seq=d.get("seq"),
        message_id=d.get("message_id"),
        from_user_id=d.get("from_user_id"),
        to_user_id=d.get("to_user_id"),
        client_id=d.get("client_id"),
        create_time_ms=d.get("create_time_ms"),
        update_time_ms=d.get("update_time_ms"),
        delete_time_ms=d.get("delete_time_ms"),
        session_id=d.get("session_id"),
        group_id=d.get("group_id"),
        message_type=d.get("message_type"),
        message_state=d.get("message_state"),
        item_list=items or None,
        context_token=d.get("context_token"),
    )


def dict_to_get_updates_resp(d: dict) -> GetUpdatesResp:
    """Parse a raw JSON dict into a :class:`GetUpdatesResp`."""
    msgs_raw = d.get("msgs")
    msgs = [dict_to_weixin_message(m) for m in msgs_raw] if msgs_raw else None
    return GetUpdatesResp(
        ret=d.get("ret"),
        errcode=d.get("errcode"),
        errmsg=d.get("errmsg"),
        msgs=msgs,
        get_updates_buf=d.get("get_updates_buf"),
        longpolling_timeout_ms=d.get("longpolling_timeout_ms"),
    )
