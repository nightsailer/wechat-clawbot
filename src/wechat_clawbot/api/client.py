"""HTTP API client for the Weixin iLink bot service."""

from __future__ import annotations

import base64
import json
import os
import struct
from dataclasses import dataclass

import httpx

from wechat_clawbot.auth.accounts import load_config_route_tag
from wechat_clawbot.util.logger import logger
from wechat_clawbot.util.redact import redact_body, redact_url

from .types import (
    GetConfigResp,
    GetUpdatesResp,
    GetUploadUrlReq,
    GetUploadUrlResp,
    SendMessageReq,
    SendTypingReq,
    _dataclass_to_dict,
    dict_to_get_updates_resp,
)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ApiHttpError(RuntimeError):
    """Structured HTTP error with status code for precise exception handling."""

    def __init__(self, status_code: int, label: str, body: str) -> None:
        super().__init__(f"{label} {status_code}: {body}")
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Timeouts
# ---------------------------------------------------------------------------

DEFAULT_LONG_POLL_TIMEOUT_MS = 35_000
DEFAULT_API_TIMEOUT_MS = 15_000
DEFAULT_CONFIG_TIMEOUT_MS = 10_000


@dataclass
class WeixinApiOptions:
    base_url: str
    token: str | None = None
    timeout_ms: int | None = None
    context_token: str | None = None


# ---------------------------------------------------------------------------
# Shared HTTP client
# ---------------------------------------------------------------------------

# Module-level shared client avoids per-request TCP connection setup/teardown.
# The long-poll timeout is set per-request, so we use a generous default here.
_shared_client: httpx.AsyncClient | None = None


def _get_shared_client() -> httpx.AsyncClient:
    """Return (and lazily create) the module-level shared httpx.AsyncClient."""
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))
    return _shared_client


async def close_shared_client() -> None:
    """Close the shared HTTP client. Call during application shutdown."""
    global _shared_client
    if _shared_client is not None and not _shared_client.is_closed:
        await _shared_client.aclose()
        _shared_client = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# channel_version 跟随上游 openclaw-weixin 版本号，而非本项目版本。
_UPSTREAM_CHANNEL_VERSION = "2.1.1"
_BASE_INFO: dict = {"channel_version": _UPSTREAM_CHANNEL_VERSION}

# iLink-App-Id: 从 package 配置读取，硬编码为 "bot"。
ILINK_APP_ID: str = "bot"


def _build_client_version(version: str) -> int:
    """iLink-App-ClientVersion: uint32 encoded as 0x00MMNNPP.

    e.g. "0.2.0" -> 0x00000200 = 512
    """
    parts = version.split(".")
    major = int(parts[0]) if len(parts) > 0 else 0
    minor = int(parts[1]) if len(parts) > 1 else 0
    patch = int(parts[2]) if len(parts) > 2 else 0
    return ((major & 0xFF) << 16) | ((minor & 0xFF) << 8) | (patch & 0xFF)


ILINK_APP_CLIENT_VERSION: int = _build_client_version(_UPSTREAM_CHANNEL_VERSION)


def _build_base_info() -> dict:
    return _BASE_INFO


def _ensure_trailing_slash(url: str) -> str:
    return url if url.endswith("/") else f"{url}/"


def _random_wechat_uin() -> str:
    """X-WECHAT-UIN header: random uint32 -> decimal string -> base64."""
    uint32 = struct.unpack(">I", os.urandom(4))[0]
    return base64.b64encode(str(uint32).encode()).decode()


def _build_common_headers() -> dict[str, str]:
    """Build headers shared by both GET and POST requests."""
    headers: dict[str, str] = {
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
    }
    route_tag = load_config_route_tag()
    if route_tag:
        headers["SKRouteTag"] = route_tag
    return headers


def _build_post_headers(token: str | None, body_bytes: bytes) -> dict[str, str]:
    headers: dict[str, str] = {
        **_build_common_headers(),
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Content-Length": str(len(body_bytes)),
        "X-WECHAT-UIN": _random_wechat_uin(),
    }
    if token and token.strip():
        headers["Authorization"] = f"Bearer {token.strip()}"
    return headers


async def api_get_fetch(
    base_url: str,
    endpoint: str,
    timeout_ms: int,
    label: str,
) -> str:
    """GET fetch wrapper for Weixin API endpoints. Returns raw response text."""
    base = _ensure_trailing_slash(base_url)
    url = f"{base}{endpoint}"
    hdrs = _build_common_headers()
    logger.debug(f"GET {redact_url(url)}")

    client = _get_shared_client()
    resp = await client.get(url, headers=hdrs, timeout=timeout_ms / 1000.0)
    raw_text = resp.text
    logger.debug(f"{label} status={resp.status_code} raw={redact_body(raw_text)}")
    if resp.status_code >= 400:
        raise ApiHttpError(resp.status_code, label, raw_text)
    return raw_text


async def _api_post_fetch(
    base_url: str,
    endpoint: str,
    body: str,
    token: str | None,
    timeout_ms: int,
    label: str,
) -> str:
    """POST JSON to a Weixin API endpoint. Returns raw response text."""
    base = _ensure_trailing_slash(base_url)
    url = f"{base}{endpoint}"
    body_bytes = body.encode("utf-8")
    hdrs = _build_post_headers(token, body_bytes)
    logger.debug(f"POST {redact_url(url)} body={redact_body(body)}")

    client = _get_shared_client()
    resp = await client.post(url, content=body_bytes, headers=hdrs, timeout=timeout_ms / 1000.0)
    raw_text = resp.text
    logger.debug(f"{label} status={resp.status_code} raw={redact_body(raw_text)}")
    if resp.status_code >= 400:
        raise ApiHttpError(resp.status_code, label, raw_text)
    return raw_text


# ---------------------------------------------------------------------------
# Public API functions
# ---------------------------------------------------------------------------


async def get_updates(
    base_url: str,
    token: str | None = None,
    get_updates_buf: str = "",
    timeout_ms: int | None = None,
) -> GetUpdatesResp:
    """Long-poll ``getUpdates``. Returns empty response on client-side timeout."""
    t = timeout_ms or DEFAULT_LONG_POLL_TIMEOUT_MS
    try:
        raw = await _api_post_fetch(
            base_url=base_url,
            endpoint="ilink/bot/getupdates",
            body=json.dumps(
                {
                    "get_updates_buf": get_updates_buf,
                    "base_info": _build_base_info(),
                }
            ),
            token=token,
            timeout_ms=t,
            label="getUpdates",
        )
        return dict_to_get_updates_resp(json.loads(raw))
    except httpx.TimeoutException:
        logger.debug(f"getUpdates: client-side timeout after {t}ms, returning empty response")
        return GetUpdatesResp(ret=0, msgs=[], get_updates_buf=get_updates_buf)


async def get_upload_url(
    req: GetUploadUrlReq,
    opts: WeixinApiOptions,
) -> GetUploadUrlResp:
    """Get a pre-signed CDN upload URL."""
    body_dict = {k: v for k, v in _dataclass_to_dict(req).items() if v is not None}  # type: ignore[union-attr]
    body_dict["base_info"] = _build_base_info()
    raw = await _api_post_fetch(
        base_url=opts.base_url,
        endpoint="ilink/bot/getuploadurl",
        body=json.dumps(body_dict),
        token=opts.token,
        timeout_ms=opts.timeout_ms or DEFAULT_API_TIMEOUT_MS,
        label="getUploadUrl",
    )
    d = json.loads(raw)
    return GetUploadUrlResp(
        upload_param=d.get("upload_param"),
        thumb_upload_param=d.get("thumb_upload_param"),
        upload_full_url=d.get("upload_full_url"),
    )


async def send_message(opts: WeixinApiOptions, body: SendMessageReq) -> None:
    """Send a single message downstream."""
    body_dict: dict = _dataclass_to_dict(body)  # type: ignore[assignment]
    body_dict["base_info"] = _build_base_info()
    await _api_post_fetch(
        base_url=opts.base_url,
        endpoint="ilink/bot/sendmessage",
        body=json.dumps(body_dict),
        token=opts.token,
        timeout_ms=opts.timeout_ms or DEFAULT_API_TIMEOUT_MS,
        label="sendMessage",
    )


async def get_config(
    opts: WeixinApiOptions,
    ilink_user_id: str,
    context_token: str | None = None,
) -> GetConfigResp:
    """Fetch bot config (includes ``typing_ticket``) for a given user."""
    raw = await _api_post_fetch(
        base_url=opts.base_url,
        endpoint="ilink/bot/getconfig",
        body=json.dumps(
            {
                "ilink_user_id": ilink_user_id,
                "context_token": context_token,
                "base_info": _build_base_info(),
            }
        ),
        token=opts.token,
        timeout_ms=opts.timeout_ms or DEFAULT_CONFIG_TIMEOUT_MS,
        label="getConfig",
    )
    d = json.loads(raw)
    return GetConfigResp(
        ret=d.get("ret"), errmsg=d.get("errmsg"), typing_ticket=d.get("typing_ticket")
    )


async def send_typing(opts: WeixinApiOptions, body: SendTypingReq) -> None:
    """Send a typing indicator to a user."""
    body_dict: dict = _dataclass_to_dict(body)  # type: ignore[assignment]
    body_dict["base_info"] = _build_base_info()
    await _api_post_fetch(
        base_url=opts.base_url,
        endpoint="ilink/bot/sendtyping",
        body=json.dumps(body_dict),
        token=opts.token,
        timeout_ms=opts.timeout_ms or DEFAULT_CONFIG_TIMEOUT_MS,
        label="sendTyping",
    )
