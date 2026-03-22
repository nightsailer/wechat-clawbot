"""CDN upload pipeline: read file -> hash -> gen AES key -> getUploadUrl -> upload -> return info."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

import httpx

from wechat_clawbot.api.client import WeixinApiOptions, get_upload_url
from wechat_clawbot.api.types import GetUploadUrlReq, UploadMediaType
from wechat_clawbot.cdn.aes_ecb import aes_ecb_padded_size, encrypt_aes_ecb
from wechat_clawbot.cdn.cdn_url import build_cdn_upload_url
from wechat_clawbot.media.mime import get_extension_from_content_type_or_url
from wechat_clawbot.util.logger import logger
from wechat_clawbot.util.random import temp_file_name
from wechat_clawbot.util.redact import redact_url

_UPLOAD_MAX_RETRIES = 3

# Shared client for CDN uploads — reuses TCP connections across calls.
_cdn_ul_client: httpx.AsyncClient | None = None


def _get_cdn_ul_client() -> httpx.AsyncClient:
    global _cdn_ul_client
    if _cdn_ul_client is None or _cdn_ul_client.is_closed:
        _cdn_ul_client = httpx.AsyncClient(timeout=60.0, follow_redirects=True)
    return _cdn_ul_client


async def close_cdn_ul_client() -> None:
    """Close the shared CDN upload client. Call during application shutdown."""
    global _cdn_ul_client
    if _cdn_ul_client is not None and not _cdn_ul_client.is_closed:
        await _cdn_ul_client.aclose()
        _cdn_ul_client = None


@dataclass
class UploadedFileInfo:
    filekey: str
    download_encrypted_query_param: str
    aeskey: str  # hex-encoded
    file_size: int  # plaintext bytes
    file_size_ciphertext: int  # encrypted bytes


async def download_remote_image_to_temp(url: str, dest_dir: str) -> str:
    """Download a remote media URL to a local temp file. Returns local path."""
    logger.debug(f"downloadRemoteImageToTemp: fetching url={url}")
    client = _get_cdn_ul_client()
    resp = await client.get(url)
    if resp.status_code >= 400:
        raise RuntimeError(f"remote media download failed: {resp.status_code} url={url}")
    buf = resp.content
    logger.debug(f"downloadRemoteImageToTemp: downloaded {len(buf)} bytes")
    Path(dest_dir).mkdir(parents=True, exist_ok=True)
    ext = get_extension_from_content_type_or_url(resp.headers.get("content-type"), url)
    name = temp_file_name("weixin-remote", ext)
    file_path = os.path.join(dest_dir, name)
    Path(file_path).write_bytes(buf)
    logger.debug(f"downloadRemoteImageToTemp: saved to {file_path}")
    return file_path


async def _upload_buffer_to_cdn(
    buf: bytes,
    upload_param: str,
    filekey: str,
    cdn_base_url: str,
    aeskey: bytes,
    label: str,
) -> str:
    """Upload one buffer to CDN with AES-128-ECB encryption. Returns download param."""
    ciphertext = encrypt_aes_ecb(buf, aeskey)
    cdn_url = build_cdn_upload_url(cdn_base_url, upload_param, filekey)
    logger.debug(f"{label}: CDN POST url={redact_url(cdn_url)} ciphertextSize={len(ciphertext)}")

    download_param: str | None = None
    last_error: Exception | None = None
    client = _get_cdn_ul_client()

    for attempt in range(1, _UPLOAD_MAX_RETRIES + 1):
        try:
            resp = await client.post(
                cdn_url,
                content=ciphertext,
                headers={"Content-Type": "application/octet-stream"},
            )
            if 400 <= resp.status_code < 500:
                err_msg = resp.headers.get("x-error-message", resp.text)
                raise RuntimeError(f"CDN upload client error {resp.status_code}: {err_msg}")
            if resp.status_code != 200:
                err_msg = resp.headers.get("x-error-message", f"status {resp.status_code}")
                raise RuntimeError(f"CDN upload server error: {err_msg}")
            download_param = resp.headers.get("x-encrypted-param")
            if not download_param:
                raise RuntimeError("CDN upload response missing x-encrypted-param header")
            logger.debug(f"{label}: CDN upload success attempt={attempt}")
            break
        except Exception as e:
            last_error = e
            if "client error" in str(e):
                raise
            if attempt < _UPLOAD_MAX_RETRIES:
                logger.error(f"{label}: attempt {attempt} failed, retrying... err={e}")
            else:
                logger.error(f"{label}: all {_UPLOAD_MAX_RETRIES} attempts failed err={e}")

    if not download_param:
        raise last_error or RuntimeError(f"CDN upload failed after {_UPLOAD_MAX_RETRIES} attempts")
    return download_param


async def _upload_media_to_cdn(
    file_path: str,
    to_user_id: str,
    opts: WeixinApiOptions,
    cdn_base_url: str,
    media_type: int,
    label: str,
) -> UploadedFileInfo:
    """Common upload pipeline."""
    plaintext = Path(file_path).read_bytes()
    rawsize = len(plaintext)
    rawfilemd5 = hashlib.md5(plaintext, usedforsecurity=False).hexdigest()
    filesize = aes_ecb_padded_size(rawsize)
    filekey = os.urandom(16).hex()
    aeskey = os.urandom(16)

    logger.debug(
        f"{label}: file={file_path} rawsize={rawsize} filesize={filesize} md5={rawfilemd5}"
    )

    upload_resp = await get_upload_url(
        req=GetUploadUrlReq(
            filekey=filekey,
            media_type=media_type,
            to_user_id=to_user_id,
            rawsize=rawsize,
            rawfilemd5=rawfilemd5,
            filesize=filesize,
            no_need_thumb=True,
            aeskey=aeskey.hex(),
        ),
        opts=opts,
    )

    upload_param = upload_resp.upload_param
    if not upload_param:
        raise RuntimeError(f"{label}: getUploadUrl returned no upload_param")

    download_param = await _upload_buffer_to_cdn(
        buf=plaintext,
        upload_param=upload_param,
        filekey=filekey,
        cdn_base_url=cdn_base_url,
        aeskey=aeskey,
        label=f"{label}[orig filekey={filekey}]",
    )

    return UploadedFileInfo(
        filekey=filekey,
        download_encrypted_query_param=download_param,
        aeskey=aeskey.hex(),
        file_size=rawsize,
        file_size_ciphertext=filesize,
    )


async def upload_file_to_weixin(
    file_path: str, to_user_id: str, opts: WeixinApiOptions, cdn_base_url: str
) -> UploadedFileInfo:
    """Upload a local image file to the Weixin CDN."""
    return await _upload_media_to_cdn(
        file_path, to_user_id, opts, cdn_base_url, UploadMediaType.IMAGE, "uploadFileToWeixin"
    )


async def upload_video_to_weixin(
    file_path: str, to_user_id: str, opts: WeixinApiOptions, cdn_base_url: str
) -> UploadedFileInfo:
    """Upload a local video file to the Weixin CDN."""
    return await _upload_media_to_cdn(
        file_path, to_user_id, opts, cdn_base_url, UploadMediaType.VIDEO, "uploadVideoToWeixin"
    )


async def upload_file_attachment_to_weixin(
    file_path: str, to_user_id: str, opts: WeixinApiOptions, cdn_base_url: str
) -> UploadedFileInfo:
    """Upload a local file attachment (non-image, non-video) to the Weixin CDN."""
    return await _upload_media_to_cdn(
        file_path,
        to_user_id,
        opts,
        cdn_base_url,
        UploadMediaType.FILE,
        "uploadFileAttachmentToWeixin",
    )
