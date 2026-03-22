"""Upload + send media file, routing by MIME type."""

from __future__ import annotations

import os

from wechat_clawbot.api.client import WeixinApiOptions
from wechat_clawbot.cdn.upload import (
    upload_file_attachment_to_weixin,
    upload_file_to_weixin,
    upload_video_to_weixin,
)
from wechat_clawbot.media.mime import get_mime_from_filename
from wechat_clawbot.messaging.send import (
    send_file_message_weixin,
    send_image_message_weixin,
    send_video_message_weixin,
)
from wechat_clawbot.util.logger import logger


async def send_weixin_media_file(
    file_path: str,
    to: str,
    text: str,
    opts: WeixinApiOptions,
    cdn_base_url: str,
) -> dict[str, str]:
    """Upload a local file and send it as a weixin message, routing by MIME type.

    - ``video/*``  -> uploadVideo + sendVideo
    - ``image/*``  -> uploadFile  + sendImage
    - else         -> uploadFileAttachment + sendFile
    """
    mime = get_mime_from_filename(file_path)
    upload_opts = WeixinApiOptions(base_url=opts.base_url, token=opts.token)

    if mime.startswith("video/"):
        logger.info(f"[weixin] sendWeixinMediaFile: uploading video filePath={file_path} to={to}")
        uploaded = await upload_video_to_weixin(file_path, to, upload_opts, cdn_base_url)
        return await send_video_message_weixin(to, text, uploaded, opts)

    if mime.startswith("image/"):
        logger.info(f"[weixin] sendWeixinMediaFile: uploading image filePath={file_path} to={to}")
        uploaded = await upload_file_to_weixin(file_path, to, upload_opts, cdn_base_url)
        return await send_image_message_weixin(to, text, uploaded, opts)

    file_name = os.path.basename(file_path)
    logger.info(f"[weixin] sendWeixinMediaFile: uploading file filePath={file_path} to={to}")
    uploaded = await upload_file_attachment_to_weixin(file_path, to, upload_opts, cdn_base_url)
    return await send_file_message_weixin(to, text, file_name, uploaded, opts)
