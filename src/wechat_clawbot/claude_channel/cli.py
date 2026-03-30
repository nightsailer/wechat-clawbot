"""CLI entry point for the WeChat Claude Code channel.

Usage:
    wechat-clawbot-cc setup   — QR login to WeChat
    wechat-clawbot-cc serve   — Start MCP channel server (for Claude Code)
    wechat-clawbot-cc serve --gateway <url> --endpoint <id>  — Bridge mode
    wechat-clawbot-cc help    — Show help
"""

from __future__ import annotations

import sys

import anyio


def _log_info(msg: str) -> None:
    print(f"[wechat-channel] {msg}", file=sys.stderr, flush=True)


def _print_help() -> None:
    print(
        """
wechat-clawbot-cc — WeChat channel for Claude Code

Commands:
  setup    微信扫码登录（首次使用前运行）
  serve    启动 MCP Channel 服务器（由 Claude Code 调用）
  help     显示此帮助信息

Options for serve:
  --gateway <url>    连接到 Gateway 的 URL（桥接模式）
  --endpoint <id>    Gateway 中的端点 ID（桥接模式必填）
  --api-key <key>    Gateway 认证密钥（可选）

Quick start (direct mode):
  1. wechat-clawbot-cc setup
  2. claude mcp add wechat -- wechat-clawbot-cc serve
  3. claude --dangerously-load-development-channels server:wechat

Quick start (bridge mode):
  claude mcp add wechat -- wechat-clawbot-cc serve --gateway http://localhost:8765 --endpoint claude
  claude --dangerously-load-development-channels server:wechat
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

        anyio.run(interactive_setup)
        return

    if command == "serve":
        # Parse optional --gateway, --endpoint, --api-key flags
        gateway_url = None
        endpoint_id = None
        api_key = ""
        i = 1
        while i < len(args):
            if args[i] == "--gateway" and i + 1 < len(args):
                gateway_url = args[i + 1]
                i += 2
            elif args[i] == "--endpoint" and i + 1 < len(args):
                endpoint_id = args[i + 1]
                i += 2
            elif args[i] == "--api-key" and i + 1 < len(args):
                api_key = args[i + 1]
                i += 2
            else:
                i += 1

        if gateway_url:
            # Bridge mode — connect to gateway SSE instead of polling WeChat directly
            if not endpoint_id:
                print(
                    "[wechat-bridge] --endpoint is required with --gateway",
                    file=sys.stderr,
                )
                sys.exit(1)
            from .bridge import run_bridge_server

            _log_info(f"Bridge mode: gateway={gateway_url} endpoint={endpoint_id}")
            anyio.run(run_bridge_server, gateway_url, endpoint_id, api_key)
        else:
            # Direct mode — poll WeChat directly
            from .credentials import load_credentials
            from .server import run_channel_server

            account = load_credentials()
            if not account:
                print(
                    "[wechat-channel] 未找到凭据，请先运行: wechat-clawbot-cc setup",
                    file=sys.stderr,
                )
                sys.exit(1)
            _log_info(f"使用已保存账号: {account.account_id}")
            anyio.run(run_channel_server, account)
        return

    print(f"未知命令: {command}", file=sys.stderr)
    _print_help()
    sys.exit(1)
