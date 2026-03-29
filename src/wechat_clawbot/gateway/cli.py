"""Gateway CLI — command-line interface for managing the gateway."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from .config import (
    load_gateway_config,
    resolve_gateway_state_dir,
    scaffold_gateway_config,
)


def main() -> None:
    """Entry point for clawbot-gateway CLI."""
    parser = argparse.ArgumentParser(
        prog="clawbot-gateway",
        description="WeChat ClawBot Gateway — M:N message routing gateway",
    )
    parser.add_argument("--config", type=Path, help="Path to gateway.yaml")
    parser.add_argument("--json", action="store_true", dest="json_output", help="JSON output")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmations")

    sub = parser.add_subparsers(dest="command")

    # init
    sub.add_parser("init", help="Initialize gateway configuration")

    # start
    sub.add_parser("start", help="Start the gateway")

    # stop
    sub.add_parser("stop", help="Stop the running gateway")

    # status
    sub.add_parser("status", help="Show gateway status")

    # account
    account_parser = sub.add_parser("account", help="Bot account management")
    account_sub = account_parser.add_subparsers(dest="account_command")
    account_sub.add_parser("add", help="Add a Bot account via QR login")

    args = parser.parse_args()

    if args.command == "init":
        _cmd_init(args)
    elif args.command == "start":
        _cmd_start(args)
    elif args.command == "stop":
        _cmd_stop(args)
    elif args.command == "status":
        _cmd_status(args)
    elif args.command == "account":
        if args.account_command == "add":
            _cmd_account_add(args)
        else:
            account_parser.print_help()
    else:
        parser.print_help()


def _cmd_init(args: argparse.Namespace) -> None:
    """Initialize gateway configuration."""
    state_dir = resolve_gateway_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)

    config_path = scaffold_gateway_config(state_dir)
    print(f"Gateway initialized at {state_dir}")
    print(f"Configuration: {config_path}")
    print()
    print("Next steps:")
    print("  1. Edit gateway.yaml to configure accounts and endpoints")
    print("  2. Run: clawbot-gateway account add")
    print("  3. Run: clawbot-gateway start")


def _cmd_start(args: argparse.Namespace) -> None:
    """Start the gateway."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(name)s: %(message)s",
    )

    try:
        config = load_gateway_config(args.config)
    except Exception as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        sys.exit(1)

    from .app import GatewayApp

    app = GatewayApp(config)
    try:
        asyncio.run(app.start())
    except KeyboardInterrupt:
        print("\nGateway shutting down...")
        asyncio.run(app.stop())


def _cmd_stop(args: argparse.Namespace) -> None:
    """Stop the running gateway."""
    # Phase 1: simple message, will use Admin API in Phase 5
    print("Stop not yet implemented — use Ctrl+C to stop the running gateway")


def _cmd_status(args: argparse.Namespace) -> None:
    """Show gateway status."""
    state_dir = resolve_gateway_state_dir()
    config_path = state_dir / "gateway.yaml"

    if not config_path.exists():
        print("Gateway not initialized. Run: clawbot-gateway init")
        return

    try:
        config = load_gateway_config()
        print("Gateway Configuration:")
        print(f"  Host: {config.gateway.host}:{config.gateway.port}")
        print(f"  Accounts: {len(config.accounts)}")
        print(f"  Endpoints: {len(config.endpoints)}")
        for eid, ecfg in config.endpoints.items():
            print(f"    - {eid}: {ecfg.name} ({ecfg.type})")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)


def _cmd_account_add(args: argparse.Namespace) -> None:
    """Add a Bot account via QR login."""
    state_dir = resolve_gateway_state_dir()
    accounts_dir = state_dir / "accounts"
    accounts_dir.mkdir(parents=True, exist_ok=True)

    print("Starting QR login...")
    asyncio.run(_do_account_add(accounts_dir))


async def _do_account_add(accounts_dir: Path) -> None:
    """Async QR login flow."""
    from wechat_clawbot.claude_channel.setup import do_qr_login

    result = await do_qr_login()
    if result:
        # Save credentials to gateway accounts directory
        cred_file = accounts_dir / f"{result.account_id}.json"
        cred_data = {
            "token": result.token,
            "baseUrl": result.base_url,
            "accountId": result.account_id,
            "userId": result.user_id,
        }
        cred_file.write_text(json.dumps(cred_data, indent=2))
        cred_file.chmod(0o600)
        print(f"\nAccount saved: {cred_file}")
        print(f"Account ID: {result.account_id}")
    else:
        print("Login failed or cancelled.", file=sys.stderr)
