"""Gateway CLI — command-line interface for managing the gateway."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
from pathlib import Path

from .config import (
    load_gateway_config,
    resolve_gateway_state_dir,
    scaffold_gateway_config,
)

_PID_FILE_NAME = "gateway.pid"


def _output(args: argparse.Namespace, data: dict | list | str) -> None:
    """Output data, respecting --json flag."""
    if getattr(args, "json_output", False):
        if isinstance(data, str):
            data = {"message": data}
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        if isinstance(data, str):
            print(data)
        elif isinstance(data, dict):
            for k, v in data.items():
                print(f"  {k}: {v}")
        elif isinstance(data, list):
            for item in data:
                print(f"  - {item}")


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
    _output(
        args,
        {
            "state_dir": str(state_dir),
            "config_path": str(config_path),
            "status": "initialized",
        },
    )
    if not args.json_output:
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

    # Write PID file
    state_dir = resolve_gateway_state_dir()
    pid_file = state_dir / _PID_FILE_NAME
    pid_file.write_text(str(os.getpid()))

    from .app import GatewayApp

    app = GatewayApp(config)
    try:
        asyncio.run(app.start())
    except KeyboardInterrupt:
        print("\nGateway shutting down...")
        asyncio.run(app.stop())
    finally:
        pid_file.unlink(missing_ok=True)


def _cmd_stop(args: argparse.Namespace) -> None:
    """Stop the running gateway via PID file."""
    state_dir = resolve_gateway_state_dir()
    pid_file = state_dir / _PID_FILE_NAME

    if not pid_file.exists():
        _output(args, "No running gateway found (PID file missing)")
        return

    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, signal.SIGINT)
        _output(args, {"status": "stop signal sent", "pid": pid})
    except ProcessLookupError:
        pid_file.unlink(missing_ok=True)
        _output(args, "Gateway process not found (stale PID file removed)")
    except ValueError:
        _output(args, "Invalid PID file")


def _cmd_status(args: argparse.Namespace) -> None:
    """Show gateway status."""
    state_dir = resolve_gateway_state_dir()
    config_path = state_dir / "gateway.yaml"

    if not config_path.exists():
        _output(args, "Gateway not initialized. Run: clawbot-gateway init")
        return

    # Check if running
    pid_file = state_dir / _PID_FILE_NAME
    running = False
    pid = None
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)  # Check if process exists
            running = True
        except (ProcessLookupError, ValueError):
            running = False

    try:
        config = load_gateway_config()
        endpoints = {
            eid: {"name": ecfg.name, "type": ecfg.type} for eid, ecfg in config.endpoints.items()
        }
        status_data = {
            "running": running,
            "pid": pid if running else None,
            "host": f"{config.gateway.host}:{config.gateway.port}",
            "accounts": len(config.accounts),
            "endpoints": endpoints,
        }
        _output(args, status_data)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)


def _cmd_account_add(args: argparse.Namespace) -> None:
    """Add a Bot account via QR login."""
    state_dir = resolve_gateway_state_dir()
    accounts_dir = state_dir / "accounts"
    accounts_dir.mkdir(parents=True, exist_ok=True)

    if not args.json_output:
        print("Starting QR login...")
    asyncio.run(_do_account_add(accounts_dir, args))


async def _do_account_add(accounts_dir: Path, args: argparse.Namespace) -> None:
    """Async QR login flow."""
    from wechat_clawbot.claude_channel.setup import do_qr_login

    result = await do_qr_login()
    if result:
        cred_file = accounts_dir / f"{result.account_id}.json"
        cred_data = {
            "token": result.token,
            "baseUrl": result.base_url,
            "accountId": result.account_id,
            "userId": result.user_id,
        }
        cred_file.write_text(json.dumps(cred_data, indent=2))
        cred_file.chmod(0o600)
        _output(
            args,
            {
                "status": "saved",
                "account_id": result.account_id,
                "credentials_path": str(cred_file),
            },
        )
    else:
        print("Login failed or cancelled.", file=sys.stderr)
