"""Download and decrypt media from a single MessageItem."""

from __future__ import annotations

import base64
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from wechat_clawbot.api.types import MessageItemType
from wechat_clawbot.cdn.download import download_and_decrypt_buffer, download_plain_cdn_buffer
from wechat_clawbot.media.mime import get_mime_from_filename
from wechat_clawbot.media.silk import silk_to_wav
from wechat_clawbot.util.logger import logger

if TYPE_CHECKING:
    from wechat_clawbot.api.types import MessageItem

_WEIXIN_MEDIA_MAX_BYTES = 100 * 1024 * 1024

# Callback type: (buffer, content_type, subdir, max_bytes, original_filename) -> {path}
SaveMediaFn = Callable[..., Awaitable[dict[str, str]]]


class InboundMediaOpts:
    """Populated fields from media download/decrypt."""

    __slots__ = (
        "decrypted_pic_path",
        "decrypted_voice_path",
        "voice_media_type",
        "decrypted_file_path",
        "file_media_type",
        "decrypted_video_path",
    )

    def __init__(self) -> None:
        self.decrypted_pic_path: str | None = None
        self.decrypted_voice_path: str | None = None
        self.voice_media_type: str | None = None
        self.decrypted_file_path: str | None = None
        self.file_media_type: str | None = None
        self.decrypted_video_path: str | None = None


async def download_media_from_item(
    item: MessageItem,
    cdn_base_url: str,
    save_media: SaveMediaFn,
    log: Callable[[str], None],
    err_log: Callable[[str], None],
    label: str,
) -> InboundMediaOpts:
    """Download and decrypt media from a single :class:`MessageItem`."""
    result = InboundMediaOpts()

    if item.type == MessageItemType.IMAGE:
        img = item.image_item
        if not img or not img.media or not img.media.encrypt_query_param:
            return result
        aes_key_b64: str | None = None
        if img.aeskey:
            aes_key_b64 = base64.b64encode(bytes.fromhex(img.aeskey)).decode()
        else:
            aes_key_b64 = img.media.aes_key
        try:
            if aes_key_b64:
                buf = await download_and_decrypt_buffer(
                    img.media.encrypt_query_param, aes_key_b64, cdn_base_url, f"{label} image"
                )
            else:
                buf = await download_plain_cdn_buffer(
                    img.media.encrypt_query_param, cdn_base_url, f"{label} image-plain"
                )
            saved = await save_media(buf, None, "inbound", _WEIXIN_MEDIA_MAX_BYTES)
            result.decrypted_pic_path = saved["path"]
        except Exception as e:
            logger.error(f"{label} image download/decrypt failed: {e}")
            err_log(f"weixin {label} image download/decrypt failed: {e}")

    elif item.type == MessageItemType.VOICE:
        voice = item.voice_item
        if (
            not voice
            or not voice.media
            or not voice.media.encrypt_query_param
            or not voice.media.aes_key
        ):
            return result
        try:
            silk_buf = await download_and_decrypt_buffer(
                voice.media.encrypt_query_param, voice.media.aes_key, cdn_base_url, f"{label} voice"
            )
            wav_buf = await silk_to_wav(silk_buf)
            if wav_buf:
                saved = await save_media(wav_buf, "audio/wav", "inbound", _WEIXIN_MEDIA_MAX_BYTES)
                result.decrypted_voice_path = saved["path"]
                result.voice_media_type = "audio/wav"
            else:
                saved = await save_media(silk_buf, "audio/silk", "inbound", _WEIXIN_MEDIA_MAX_BYTES)
                result.decrypted_voice_path = saved["path"]
                result.voice_media_type = "audio/silk"
        except Exception as e:
            logger.error(f"{label} voice download/transcode failed: {e}")
            err_log(f"weixin {label} voice download/transcode failed: {e}")

    elif item.type == MessageItemType.FILE:
        file_item = item.file_item
        if (
            not file_item
            or not file_item.media
            or not file_item.media.encrypt_query_param
            or not file_item.media.aes_key
        ):
            return result
        try:
            buf = await download_and_decrypt_buffer(
                file_item.media.encrypt_query_param,
                file_item.media.aes_key,
                cdn_base_url,
                f"{label} file",
            )
            mime = get_mime_from_filename(file_item.file_name or "file.bin")
            saved = await save_media(
                buf, mime, "inbound", _WEIXIN_MEDIA_MAX_BYTES, file_item.file_name
            )
            result.decrypted_file_path = saved["path"]
            result.file_media_type = mime
        except Exception as e:
            logger.error(f"{label} file download failed: {e}")
            err_log(f"weixin {label} file download failed: {e}")

    elif item.type == MessageItemType.VIDEO:
        video = item.video_item
        if (
            not video
            or not video.media
            or not video.media.encrypt_query_param
            or not video.media.aes_key
        ):
            return result
        try:
            buf = await download_and_decrypt_buffer(
                video.media.encrypt_query_param,
                video.media.aes_key,
                cdn_base_url,
                f"{label} video",
            )
            saved = await save_media(buf, "video/mp4", "inbound", _WEIXIN_MEDIA_MAX_BYTES)
            result.decrypted_video_path = saved["path"]
        except Exception as e:
            logger.error(f"{label} video download failed: {e}")
            err_log(f"weixin {label} video download failed: {e}")

    return result
