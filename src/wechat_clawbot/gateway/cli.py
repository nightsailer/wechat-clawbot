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
_ENV_GATEWAY_URL = "CLAWBOT_GATEWAY_URL"


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


def _get_gateway_url(args: argparse.Namespace) -> str | None:
    """Resolve the remote gateway URL from CLI flag or env var."""
    url = getattr(args, "gateway", None) or os.environ.get(_ENV_GATEWAY_URL) or ""
    return url.rstrip("/") if url else None


def _get_admin_token(args: argparse.Namespace) -> str:
    """Resolve admin token from CLI flag or env var."""
    return getattr(args, "admin_token", "") or os.environ.get("CLAWBOT_ADMIN_TOKEN", "")


def _remote_request(
    method: str,
    gateway_url: str,
    path: str,
    token: str = "",
    body: dict | None = None,
) -> dict:
    """Make a synchronous HTTP request to the admin API."""
    import httpx  # noqa: PLC0415

    url = f"{gateway_url}{path}"
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    with httpx.Client(timeout=10) as client:
        if method == "GET":
            resp = client.get(url, headers=headers)
        elif method == "POST":
            resp = client.post(url, headers=headers, json=body or {})
        elif method == "DELETE":
            resp = client.delete(url, headers=headers)
        else:
            raise ValueError(f"Unsupported method: {method}")

    try:
        return resp.json()
    except Exception:
        return {"status_code": resp.status_code, "text": resp.text}


def main() -> None:
    """Entry point for clawbot-gateway CLI."""
    parser = argparse.ArgumentParser(
        prog="clawbot-gateway",
        description="WeChat ClawBot Gateway — M:N message routing gateway",
    )
    parser.add_argument("--config", type=Path, help="Path to gateway.yaml")
    parser.add_argument("--json", action="store_true", dest="json_output", help="JSON output")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmations")
    parser.add_argument(
        "--gateway",
        type=str,
        default="",
        help="Remote gateway admin URL (or set CLAWBOT_GATEWAY_URL)",
    )
    parser.add_argument(
        "--admin-token",
        type=str,
        default="",
        help="Bearer token for admin API (or set CLAWBOT_ADMIN_TOKEN)",
    )

    sub = parser.add_subparsers(dest="command")

    # init
    sub.add_parser("init", help="Initialize gateway configuration")

    # start
    sub.add_parser("start", help="Start the gateway")

    # stop
    sub.add_parser("stop", help="Stop the running gateway")

    # status
    sub.add_parser("status", help="Show gateway status")

    # ---- account subcommands ---------------------------------------------------
    account_parser = sub.add_parser("account", help="Bot account management")
    account_sub = account_parser.add_subparsers(dest="account_command")
    account_sub.add_parser("add", help="Add a Bot account via QR login")
    account_sub.add_parser("list", help="List configured Bot accounts")
    account_rm = account_sub.add_parser("remove", help="Remove a Bot account")
    account_rm.add_argument("account_id", help="Account ID to remove")
    account_st = account_sub.add_parser("status", help="Show account status")
    account_st.add_argument("account_id", nargs="?", help="Account ID (optional)")

    # ---- user subcommands ------------------------------------------------------
    user_parser = sub.add_parser("user", help="User management")
    user_sub = user_parser.add_subparsers(dest="user_command")
    user_sub.add_parser("list", help="List all users")
    user_info_p = user_sub.add_parser("info", help="Show user info")
    user_info_p.add_argument("user_id", help="User ID")
    user_allow_p = user_sub.add_parser("allow", help="Allow a user (add to allowlist)")
    user_allow_p.add_argument("user_id", help="User ID to allow")
    user_block_p = user_sub.add_parser("block", help="Block a user")
    user_block_p.add_argument("user_id", help="User ID to block")
    user_bind_p = user_sub.add_parser("bind", help="Bind user to an endpoint")
    user_bind_p.add_argument("user_id", help="User ID")
    user_bind_p.add_argument("endpoint_id", help="Endpoint ID")
    user_unbind_p = user_sub.add_parser("unbind", help="Unbind user from an endpoint")
    user_unbind_p.add_argument("user_id", help="User ID")
    user_unbind_p.add_argument("endpoint_id", help="Endpoint ID")

    # ---- endpoint subcommands --------------------------------------------------
    ep_parser = sub.add_parser("endpoint", help="Endpoint management")
    ep_sub = ep_parser.add_subparsers(dest="endpoint_command")
    ep_sub.add_parser("list", help="List endpoints")
    ep_add_p = ep_sub.add_parser("add", help="Add an endpoint")
    ep_add_p.add_argument("endpoint_id", help="Endpoint ID")
    ep_add_p.add_argument("--name", default="", help="Display name")
    ep_add_p.add_argument("--type", default="mcp", dest="ep_type", help="Channel type")
    ep_add_p.add_argument("--url", default="", help="Endpoint URL")
    ep_rm_p = ep_sub.add_parser("remove", help="Remove an endpoint")
    ep_rm_p.add_argument("endpoint_id", help="Endpoint ID")

    # ---- invite subcommands ----------------------------------------------------
    invite_parser = sub.add_parser("invite", help="Invite code management")
    invite_sub = invite_parser.add_subparsers(dest="invite_command")
    invite_sub.add_parser("list", help="List active invite codes")
    invite_create_p = invite_sub.add_parser("create", help="Create an invite code")
    invite_create_p.add_argument("endpoint_id", help="Endpoint to bind on redeem")
    invite_create_p.add_argument("--max-uses", type=int, default=1, help="Max uses (0=unlimited)")
    invite_create_p.add_argument("--ttl", type=float, default=0, help="TTL in hours (0=no expiry)")

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
        _dispatch_account(args, account_parser)
    elif args.command == "user":
        _dispatch_user(args, user_parser)
    elif args.command == "endpoint":
        _dispatch_endpoint(args, ep_parser)
    elif args.command == "invite":
        _dispatch_invite(args, invite_parser)
    else:
        parser.print_help()


# ---------------------------------------------------------------------------
# Top-level commands
# ---------------------------------------------------------------------------


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
    """Show gateway status — remote or local."""
    gw_url = _get_gateway_url(args)
    if gw_url:
        token = _get_admin_token(args)
        data = _remote_request("GET", gw_url, "/api/status", token=token)
        _output(args, data)
        return

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


# ---------------------------------------------------------------------------
# Account subcommands
# ---------------------------------------------------------------------------


def _dispatch_account(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """Dispatch account subcommands."""
    cmd = args.account_command
    if cmd == "add":
        _cmd_account_add(args)
    elif cmd == "list":
        _cmd_account_list(args)
    elif cmd == "remove":
        _cmd_account_remove(args)
    elif cmd == "status":
        _cmd_account_status(args)
    else:
        parser.print_help()


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


def _cmd_account_list(args: argparse.Namespace) -> None:
    """List configured Bot accounts."""
    gw_url = _get_gateway_url(args)
    if gw_url:
        token = _get_admin_token(args)
        data = _remote_request("GET", gw_url, "/api/accounts", token=token)
        _output(args, data)
        return

    try:
        config = load_gateway_config(args.config)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return

    accounts = []
    for aid, acfg in config.accounts.items():
        accounts.append(
            {
                "id": aid,
                "base_url": acfg.base_url,
                "has_token": bool(acfg.token),
                "has_credentials": bool(acfg.credentials),
            }
        )
    _output(args, {"accounts": accounts})


def _cmd_account_remove(args: argparse.Namespace) -> None:
    """Remove a Bot account."""
    _output(
        args,
        f"Account removal must be done by editing gateway.yaml (remove '{args.account_id}')",
    )


def _cmd_account_status(args: argparse.Namespace) -> None:
    """Show account status."""
    gw_url = _get_gateway_url(args)
    if gw_url:
        token = _get_admin_token(args)
        data = _remote_request("GET", gw_url, "/api/status", token=token)
        _output(args, data)
        return
    _output(args, "Account status requires a running gateway. Use --gateway <url>.")


# ---------------------------------------------------------------------------
# User subcommands
# ---------------------------------------------------------------------------


def _dispatch_user(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """Dispatch user subcommands."""
    cmd = args.user_command
    if cmd == "list":
        _cmd_user_list(args)
    elif cmd == "info":
        _cmd_user_info(args)
    elif cmd == "allow":
        _cmd_user_allow(args)
    elif cmd == "block":
        _cmd_user_block(args)
    elif cmd == "bind":
        _cmd_user_bind(args)
    elif cmd == "unbind":
        _cmd_user_unbind(args)
    else:
        parser.print_help()


def _cmd_user_list(args: argparse.Namespace) -> None:
    """List all users."""
    gw_url = _get_gateway_url(args)
    if gw_url:
        token = _get_admin_token(args)
        data = _remote_request("GET", gw_url, "/api/users", token=token)
        _output(args, data)
        return
    _output(args, "User listing requires a running gateway. Use --gateway <url>.")


def _cmd_user_info(args: argparse.Namespace) -> None:
    """Show user info."""
    gw_url = _get_gateway_url(args)
    if gw_url:
        token = _get_admin_token(args)
        data = _remote_request("GET", gw_url, "/api/users", token=token)
        # Filter to specific user from list
        if isinstance(data, dict) and "users" in data:
            user = next((u for u in data["users"] if u["user_id"] == args.user_id), None)
            if user:
                _output(args, user)
            else:
                _output(args, f"User not found: {args.user_id}")
        else:
            _output(args, data)
        return
    _output(args, "User info requires a running gateway. Use --gateway <url>.")


def _cmd_user_allow(args: argparse.Namespace) -> None:
    """Allow a user (administrative)."""
    _output(
        args,
        f"To allow user '{args.user_id}', add them to the admins list in gateway.yaml "
        "or use invite-code mode.",
    )


def _cmd_user_block(args: argparse.Namespace) -> None:
    """Block a user (administrative)."""
    _output(
        args,
        f"To block user '{args.user_id}', remove them from the admins list in gateway.yaml.",
    )


def _cmd_user_bind(args: argparse.Namespace) -> None:
    """Bind a user to an endpoint."""
    gw_url = _get_gateway_url(args)
    if gw_url:
        token = _get_admin_token(args)
        data = _remote_request(
            "POST",
            gw_url,
            f"/api/users/{args.user_id}/bind",
            token=token,
            body={"endpoint_id": args.endpoint_id},
        )
        _output(args, data)
        return
    _output(args, "User binding requires a running gateway. Use --gateway <url>.")


def _cmd_user_unbind(args: argparse.Namespace) -> None:
    """Unbind a user from an endpoint."""
    gw_url = _get_gateway_url(args)
    if gw_url:
        token = _get_admin_token(args)
        data = _remote_request(
            "POST",
            gw_url,
            f"/api/users/{args.user_id}/unbind",
            token=token,
            body={"endpoint_id": args.endpoint_id},
        )
        _output(args, data)
        return
    _output(args, "User unbinding requires a running gateway. Use --gateway <url>.")


# ---------------------------------------------------------------------------
# Endpoint subcommands
# ---------------------------------------------------------------------------


def _dispatch_endpoint(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """Dispatch endpoint subcommands."""
    cmd = args.endpoint_command
    if cmd == "list":
        _cmd_endpoint_list(args)
    elif cmd == "add":
        _cmd_endpoint_add(args)
    elif cmd == "remove":
        _cmd_endpoint_remove(args)
    else:
        parser.print_help()


def _cmd_endpoint_list(args: argparse.Namespace) -> None:
    """List endpoints."""
    gw_url = _get_gateway_url(args)
    if gw_url:
        token = _get_admin_token(args)
        data = _remote_request("GET", gw_url, "/api/endpoints", token=token)
        _output(args, data)
        return

    try:
        config = load_gateway_config(args.config)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return

    endpoints = []
    for eid, ecfg in config.endpoints.items():
        endpoints.append(
            {
                "id": eid,
                "name": ecfg.name or eid,
                "type": ecfg.type.value,
            }
        )
    _output(args, {"endpoints": endpoints})


def _cmd_endpoint_add(args: argparse.Namespace) -> None:
    """Add an endpoint via admin API."""
    gw_url = _get_gateway_url(args)
    if gw_url:
        token = _get_admin_token(args)
        data = _remote_request(
            "POST",
            gw_url,
            "/api/endpoints",
            token=token,
            body={
                "id": args.endpoint_id,
                "name": args.name or args.endpoint_id,
                "type": args.ep_type,
                "url": args.url,
            },
        )
        _output(args, data)
        return
    _output(args, "Endpoint add requires a running gateway. Use --gateway <url>.")


def _cmd_endpoint_remove(args: argparse.Namespace) -> None:
    """Remove an endpoint via admin API."""
    gw_url = _get_gateway_url(args)
    if gw_url:
        token = _get_admin_token(args)
        data = _remote_request(
            "DELETE",
            gw_url,
            f"/api/endpoints/{args.endpoint_id}",
            token=token,
        )
        _output(args, data)
        return
    _output(args, "Endpoint remove requires a running gateway. Use --gateway <url>.")


# ---------------------------------------------------------------------------
# Invite subcommands
# ---------------------------------------------------------------------------


def _dispatch_invite(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """Dispatch invite subcommands."""
    cmd = args.invite_command
    if cmd == "list":
        _cmd_invite_list(args)
    elif cmd == "create":
        _cmd_invite_create(args)
    else:
        parser.print_help()


def _cmd_invite_list(args: argparse.Namespace) -> None:
    """List active invite codes."""
    gw_url = _get_gateway_url(args)
    if gw_url:
        token = _get_admin_token(args)
        data = _remote_request("GET", gw_url, "/api/invites", token=token)
        _output(args, data)
        return
    _output(args, "Invite list requires a running gateway. Use --gateway <url>.")


def _cmd_invite_create(args: argparse.Namespace) -> None:
    """Create a new invite code."""
    gw_url = _get_gateway_url(args)
    if gw_url:
        token = _get_admin_token(args)
        data = _remote_request(
            "POST",
            gw_url,
            "/api/invites",
            token=token,
            body={
                "endpoint_id": args.endpoint_id,
                "max_uses": args.max_uses,
                "ttl_hours": args.ttl,
            },
        )
        _output(args, data)
        return
    _output(args, "Invite create requires a running gateway. Use --gateway <url>.")
