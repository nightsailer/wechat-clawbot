"""CDN download and AES-128-ECB decryption for Weixin media."""

from __future__ import annotations

import re

import httpx

from wechat_clawbot.cdn.aes_ecb import decrypt_aes_ecb
from wechat_clawbot.cdn.cdn_url import build_cdn_download_url
from wechat_clawbot.util.logger import logger

# Shared client for CDN downloads — reuses TCP connections across calls.
_cdn_dl_client: httpx.AsyncClient | None = None


def _get_cdn_dl_client() -> httpx.AsyncClient:
    global _cdn_dl_client
    if _cdn_dl_client is None or _cdn_dl_client.is_closed:
        _cdn_dl_client = httpx.AsyncClient(timeout=60.0)
    return _cdn_dl_client


async def close_cdn_dl_client() -> None:
    """Close the shared CDN download client. Call during application shutdown."""
    global _cdn_dl_client
    if _cdn_dl_client is not None and not _cdn_dl_client.is_closed:
        await _cdn_dl_client.aclose()
        _cdn_dl_client = None


async def _fetch_cdn_bytes(url: str, label: str) -> bytes:
    """Download raw bytes from the CDN (no decryption)."""
    try:
        client = _get_cdn_dl_client()
        resp = await client.get(url)
    except Exception as e:
        logger.error(f"{label}: fetch network error url={url} err={e}")
        raise
    logger.debug(f"{label}: response status={resp.status_code} ok={resp.is_success}")
    if not resp.is_success:
        msg = f"{label}: CDN download {resp.status_code} {resp.reason_phrase}"
        logger.error(msg)
        raise RuntimeError(msg)
    return resp.content


def _parse_aes_key(aes_key_base64: str, label: str) -> bytes:
    """Parse CDNMedia.aes_key into a raw 16-byte AES key.

    Two encodings in the wild:
      - base64(raw 16 bytes) -> images
      - base64(hex string of 16 bytes) -> file/voice/video
    """
    import base64

    decoded = base64.b64decode(aes_key_base64)
    if len(decoded) == 16:
        return decoded
    if len(decoded) == 32 and re.match(rb"^[0-9a-fA-F]{32}$", decoded):
        return bytes.fromhex(decoded.decode("ascii"))
    msg = (
        f"{label}: aes_key must decode to 16 raw bytes or 32-char hex string, "
        f"got {len(decoded)} bytes"
    )
    logger.error(msg)
    raise ValueError(msg)


async def download_and_decrypt_buffer(
    encrypted_query_param: str,
    aes_key_base64: str,
    cdn_base_url: str,
    label: str,
) -> bytes:
    """Download and AES-128-ECB decrypt a CDN media file. Returns plaintext bytes."""
    key = _parse_aes_key(aes_key_base64, label)
    url = build_cdn_download_url(encrypted_query_param, cdn_base_url)
    logger.debug(f"{label}: fetching url={url}")
    encrypted = await _fetch_cdn_bytes(url, label)
    logger.debug(f"{label}: downloaded {len(encrypted)} bytes, decrypting")
    decrypted = decrypt_aes_ecb(encrypted, key)
    logger.debug(f"{label}: decrypted {len(decrypted)} bytes")
    return decrypted


async def download_plain_cdn_buffer(
    encrypted_query_param: str,
    cdn_base_url: str,
    label: str,
) -> bytes:
    """Download plain (unencrypted) bytes from the CDN."""
    url = build_cdn_download_url(encrypted_query_param, cdn_base_url)
    logger.debug(f"{label}: fetching url={url}")
    return await _fetch_cdn_bytes(url, label)
