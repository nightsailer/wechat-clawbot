"""Standalone QR login tool for the WeChat channel.

Run before starting the channel to authenticate with WeChat:
    wechat-clawbot-cc setup
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from wechat_clawbot.api.client import close_shared_client
from wechat_clawbot.auth.accounts import DEFAULT_BASE_URL
from wechat_clawbot.auth.login_qr import (
    start_weixin_login_with_qr,
    wait_for_weixin_login,
)

from .credentials import AccountData, credentials_file_path, load_credentials, save_credentials


def _log(msg: str) -> None:
    print(f"[wechat-channel] {msg}", flush=True)


async def do_qr_login(base_url: str = DEFAULT_BASE_URL) -> AccountData | None:
    """Perform interactive QR login. Returns ``AccountData`` on success."""
    _log("正在获取微信登录二维码...\n")

    try:
        start_result = await start_weixin_login_with_qr(api_base_url=base_url, force=True)

        if not start_result.qrcode_url:
            _log(f"获取二维码失败: {start_result.message}")
            return None

        # Display QR code in terminal
        try:
            import qrcode

            qr = qrcode.QRCode(box_size=1, border=1)
            qr.add_data(start_result.qrcode_url)
            qr.make(fit=True)
            qr.print_ascii(out=sys.stderr, invert=True)
        except ImportError:
            _log(f"二维码链接: {start_result.qrcode_url}")

        _log("\n请用微信扫描上方二维码...\n")

        wait_result = await wait_for_weixin_login(
            session_key=start_result.session_key,
            api_base_url=base_url,
            verbose=True,
        )

        if not wait_result.connected:
            _log(f"\n{wait_result.message}")
            return None

        if not wait_result.account_id or not wait_result.bot_token:
            _log("\n登录失败：服务器未返回完整信息。")
            return None

        account = AccountData(
            token=wait_result.bot_token,
            base_url=wait_result.base_url or base_url,
            account_id=wait_result.account_id,
            user_id=wait_result.user_id,
            saved_at=datetime.now(timezone.utc).isoformat(),
        )
        save_credentials(account)
        _log("\n✅ 微信连接成功！")
        _log(f"   账号 ID: {account.account_id}")
        _log(f"   用户 ID: {account.user_id}")
        _log(f"   凭据保存至: {credentials_file_path()}")
        return account
    finally:
        await close_shared_client()


async def interactive_setup() -> None:
    """Check existing credentials, optionally re-login, then save."""
    existing = load_credentials()
    if existing:
        _log(f"已有保存的账号: {existing.account_id}")
        _log(f"保存时间: {existing.saved_at}")
        answer = input("\n是否重新登录？(y/N) ").strip().lower()
        if answer != "y":
            _log("保持现有凭据。")
            return

    account = await do_qr_login()
    if not account:
        sys.exit(1)

    print()
    _log("现在可以启动 Claude Code 通道：")
    _log("  wechat-clawbot-cc serve")
