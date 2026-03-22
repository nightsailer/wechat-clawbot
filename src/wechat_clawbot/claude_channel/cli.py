"""CLI entry point for the WeChat Claude Code channel.

Usage:
    wechat-clawbot-cc setup   — QR login to WeChat
    wechat-clawbot-cc serve   — Start MCP channel server (for Claude Code)
    wechat-clawbot-cc help    — Show help
"""

from __future__ import annotations

import asyncio
import sys


def _print_help() -> None:
    print(
        """
wechat-clawbot-cc — WeChat channel for Claude Code

Commands:
  setup    微信扫码登录（首次使用前运行）
  serve    启动 MCP Channel 服务器（由 Claude Code 调用）
  help     显示此帮助信息

Quick start:
  1. wechat-clawbot-cc setup
  2. claude --channels "wechat-clawbot-cc serve"
""".strip()
    )


def main() -> None:
    """CLI entry point."""
    args = sys.argv[1:]
    command = args[0] if args else "help"

    if command in ("help", "--help", "-h"):
        _print_help()
        return

    if command == "setup":
        from .setup import interactive_setup

        asyncio.run(interactive_setup())
        return

    if command == "serve":
        from .credentials import load_credentials
        from .server import run_channel_server

        account = load_credentials()
        if not account:
            print(
                "[wechat-channel] 未找到凭据，请先运行: wechat-clawbot-cc setup",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"[wechat-channel] 使用已保存账号: {account.account_id}", file=sys.stderr)
        asyncio.run(run_channel_server(account))
        return

    print(f"未知命令: {command}", file=sys.stderr)
    _print_help()
    sys.exit(1)
