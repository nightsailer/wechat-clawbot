"""QR code login flow for Weixin bot authentication."""

from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from urllib.parse import quote

import httpx

from wechat_clawbot.api.client import ApiHttpError, api_get_fetch
from wechat_clawbot.util.logger import logger
from wechat_clawbot.util.redact import redact_token

_ACTIVE_LOGIN_TTL_MS = 5 * 60_000
_QR_LONG_POLL_TIMEOUT_MS = 35_000
_GET_QRCODE_TIMEOUT_MS = 5_000
DEFAULT_ILINK_BOT_TYPE = "3"
_MAX_QR_REFRESH_COUNT = 3

# Fixed API base URL for all QR code requests.
_FIXED_BASE_URL = "https://ilinkai.weixin.qq.com"


class _ActiveLogin:
    __slots__ = (
        "session_key",
        "id",
        "qrcode",
        "qrcode_url",
        "started_at",
        "bot_token",
        "status",
        "current_api_base_url",
    )

    def __init__(self, session_key: str, qrcode: str, qrcode_url: str) -> None:
        self.session_key = session_key
        self.id = str(uuid.uuid4())
        self.qrcode = qrcode
        self.qrcode_url = qrcode_url
        self.started_at = time.time() * 1000
        self.bot_token: str | None = None
        self.status: str | None = None
        self.current_api_base_url: str = _FIXED_BASE_URL

    def is_fresh(self) -> bool:
        return time.time() * 1000 - self.started_at < _ACTIVE_LOGIN_TTL_MS


_active_logins: dict[str, _ActiveLogin] = {}


class WeixinQrStartResult:
    __slots__ = ("qrcode_url", "message", "session_key")

    def __init__(self, message: str, session_key: str, qrcode_url: str | None = None) -> None:
        self.qrcode_url = qrcode_url
        self.message = message
        self.session_key = session_key


class WeixinQrWaitResult:
    __slots__ = ("connected", "bot_token", "account_id", "base_url", "user_id", "message")

    def __init__(
        self,
        connected: bool,
        message: str,
        bot_token: str | None = None,
        account_id: str | None = None,
        base_url: str | None = None,
        user_id: str | None = None,
    ) -> None:
        self.connected = connected
        self.message = message
        self.bot_token = bot_token
        self.account_id = account_id
        self.base_url = base_url
        self.user_id = user_id


def _purge_expired() -> None:
    expired = [k for k, v in _active_logins.items() if not v.is_fresh()]
    for k in expired:
        del _active_logins[k]


async def _fetch_qr_code(api_base_url: str, bot_type: str) -> dict:
    logger.info(f"Fetching QR code from: {api_base_url} bot_type={bot_type}")
    raw_text = await api_get_fetch(
        base_url=api_base_url,
        endpoint=f"ilink/bot/get_bot_qrcode?bot_type={quote(bot_type)}",
        timeout_ms=_GET_QRCODE_TIMEOUT_MS,
        label="fetchQRCode",
    )
    return json.loads(raw_text)


# HTTP status codes treated as transient gateway errors (retry-safe).
_GATEWAY_ERROR_CODES = {502, 503, 504, 524}


async def _poll_qr_status(api_base_url: str, qrcode: str) -> dict:
    logger.debug(f"Long-poll QR status from: {api_base_url} qrcode=***")
    try:
        raw_text = await api_get_fetch(
            base_url=api_base_url,
            endpoint=f"ilink/bot/get_qrcode_status?qrcode={quote(qrcode)}",
            timeout_ms=_QR_LONG_POLL_TIMEOUT_MS,
            label="pollQRStatus",
        )
        return json.loads(raw_text)
    except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as err:
        logger.warning(f"pollQRStatus: network error, will retry: {err}")
        return {"status": "wait"}
    except ApiHttpError as err:
        if err.status_code in _GATEWAY_ERROR_CODES:
            logger.warning(f"pollQRStatus: gateway error {err.status_code}, will retry")
            return {"status": "wait"}
        raise


async def start_weixin_login_with_qr(
    api_base_url: str,
    bot_type: str = DEFAULT_ILINK_BOT_TYPE,
    account_id: str | None = None,
    force: bool = False,
) -> WeixinQrStartResult:
    """Start the QR code login flow. Returns a QR URL and session key."""
    session_key = account_id or str(uuid.uuid4())
    _purge_expired()

    existing = _active_logins.get(session_key)
    if not force and existing and existing.is_fresh() and existing.qrcode_url:
        return WeixinQrStartResult(
            qrcode_url=existing.qrcode_url,
            message="二维码已就绪，请使用微信扫描。",
            session_key=session_key,
        )

    try:
        qr_resp = await _fetch_qr_code(_FIXED_BASE_URL, bot_type)
        logger.info(f"QR code received, qrcode={redact_token(qr_resp.get('qrcode'))}")

        login = _ActiveLogin(
            session_key=session_key,
            qrcode=qr_resp["qrcode"],
            qrcode_url=qr_resp.get("qrcode_img_content", ""),
        )
        _active_logins[session_key] = login
        return WeixinQrStartResult(
            qrcode_url=login.qrcode_url,
            message="使用微信扫描以下二维码，以完成连接。",
            session_key=session_key,
        )
    except Exception as e:
        logger.error(f"Failed to start Weixin login: {e}")
        return WeixinQrStartResult(message=f"Failed to start login: {e}", session_key=session_key)


async def wait_for_weixin_login(
    session_key: str,
    api_base_url: str,
    bot_type: str = DEFAULT_ILINK_BOT_TYPE,
    timeout_ms: int | None = None,
    verbose: bool = False,
) -> WeixinQrWaitResult:
    """Poll for QR scan confirmation. Returns when login completes or times out."""
    active = _active_logins.get(session_key)
    if not active:
        return WeixinQrWaitResult(connected=False, message="当前没有进行中的登录，请先发起登录。")
    if not active.is_fresh():
        _active_logins.pop(session_key, None)
        return WeixinQrWaitResult(connected=False, message="二维码已过期，请重新生成。")

    total_timeout = max(timeout_ms or 480_000, 1000)
    deadline = time.time() * 1000 + total_timeout
    scanned_printed = False
    qr_refresh_count = 1

    while time.time() * 1000 < deadline:
        try:
            current_base_url = active.current_api_base_url
            status_resp = await _poll_qr_status(current_base_url, active.qrcode)
            status = status_resp.get("status", "wait")
            active.status = status

            if status == "wait":
                if verbose:
                    sys.stdout.write(".")
                    sys.stdout.flush()
            elif status == "scaned":
                if not scanned_printed:
                    sys.stdout.write("\n👀 已扫码，在微信继续操作...\n")
                    sys.stdout.flush()
                    scanned_printed = True
            elif status == "scaned_but_redirect":
                # IDC 重定向：切换轮询 host
                redirect_host = status_resp.get("redirect_host")
                if redirect_host:
                    new_base_url = f"https://{redirect_host}"
                    active.current_api_base_url = new_base_url
                    logger.info(
                        f"waitForWeixinLogin: IDC redirect, "
                        f"switching polling host to {redirect_host}"
                    )
                else:
                    logger.warning(
                        "waitForWeixinLogin: received scaned_but_redirect "
                        "but redirect_host is missing, continuing with current host"
                    )
            elif status == "expired":
                qr_refresh_count += 1
                if qr_refresh_count > _MAX_QR_REFRESH_COUNT:
                    _active_logins.pop(session_key, None)
                    return WeixinQrWaitResult(
                        connected=False, message="登录超时：二维码多次过期，请重新开始登录流程。"
                    )
                sys.stdout.write(
                    f"\n⏳ 二维码已过期，正在刷新...({qr_refresh_count}/{_MAX_QR_REFRESH_COUNT})\n"
                )
                sys.stdout.flush()
                try:
                    qr_resp = await _fetch_qr_code(_FIXED_BASE_URL, bot_type)
                    active.qrcode = qr_resp["qrcode"]
                    active.qrcode_url = qr_resp.get("qrcode_img_content", "")
                    active.started_at = time.time() * 1000
                    scanned_printed = False
                    sys.stdout.write("🔄 新二维码已生成，请重新扫描\n\n")
                    sys.stdout.flush()
                    if active.qrcode_url:
                        sys.stdout.write("如果二维码未能成功展示，请用浏览器打开以下链接扫码：\n")
                        sys.stdout.write(f"{active.qrcode_url}\n")
                    else:
                        sys.stdout.write("二维码链接未能获取，请重新开始登录流程。\n")
                    sys.stdout.flush()
                except Exception as e:
                    _active_logins.pop(session_key, None)
                    return WeixinQrWaitResult(connected=False, message=f"刷新二维码失败: {e}")
            elif status == "confirmed":
                bot_id = status_resp.get("ilink_bot_id")
                if not bot_id:
                    _active_logins.pop(session_key, None)
                    return WeixinQrWaitResult(
                        connected=False, message="登录失败：服务器未返回 ilink_bot_id。"
                    )
                _active_logins.pop(session_key, None)
                logger.info(f"Login confirmed! ilink_bot_id={bot_id}")
                return WeixinQrWaitResult(
                    connected=True,
                    message="✅ 与微信连接成功！",
                    bot_token=status_resp.get("bot_token"),
                    account_id=bot_id,
                    base_url=status_resp.get("baseurl"),
                    user_id=status_resp.get("ilink_user_id"),
                )
        except Exception as e:
            _active_logins.pop(session_key, None)
            return WeixinQrWaitResult(connected=False, message=f"Login failed: {e}")

        await asyncio.sleep(1.0)

    _active_logins.pop(session_key, None)
    return WeixinQrWaitResult(connected=False, message="登录超时，请重试。")
