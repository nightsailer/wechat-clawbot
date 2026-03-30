"""Gateway command handlers.

Processes gateway-level slash commands (``/list``, ``/use``, ``/status``,
``/bind``, ``/unbind``, ``/help``, ``/admin``) and returns plain-text
responses suitable for WeChat (no markdown).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .auth import AuthZModule
    from .endpoint_manager import EndpointManager
    from .session import SessionStore

logger = logging.getLogger(__name__)


@dataclass
class GatewayCommandContext:
    """Context passed to every command handler."""

    sender_id: str
    account_id: str
    command: str
    args: str
    session_store: SessionStore
    endpoint_manager: EndpointManager
    authz: AuthZModule


async def handle_command(ctx: GatewayCommandContext) -> str:
    """Dispatch to the appropriate command handler, return response text."""
    handlers = {
        "list": _handle_list,
        "use": _handle_use,
        "status": _handle_status,
        "bind": _handle_bind,
        "unbind": _handle_unbind,
        "help": _handle_help,
        "admin": _handle_admin,
    }
    handler = handlers.get(ctx.command)
    if handler is None:
        return f"Unknown command: /{ctx.command}\nType /help for available commands."
    return await handler(ctx)


async def _handle_list(ctx: GatewayCommandContext) -> str:
    """List user's bound endpoints with online/offline status."""
    user = ctx.session_store.get_user(ctx.sender_id)
    if user is None:
        return "User not found."

    bound_ids = [b.endpoint_id for b in user.bindings]
    if not bound_ids:
        return "You have no bound endpoints.\nUse /bind <name> to bind one."

    lines = ["Your endpoints:"]
    for eid in bound_ids:
        info = ctx.endpoint_manager.get_endpoint(eid)
        if info is None:
            status_str = "unknown"
            name = eid
        else:
            status_str = info.status.value
            name = info.config.name or eid

        active_marker = " (active)" if eid == user.active_endpoint else ""
        status_icon = "[online]" if status_str == "online" else "[offline]"
        if status_str == "error":
            status_icon = "[error]"
        lines.append(f"  {name} {status_icon}{active_marker}")

    return "\n".join(lines)


async def _handle_use(ctx: GatewayCommandContext) -> str:
    """Switch active endpoint."""
    target = ctx.args.strip()
    if not target:
        return "Usage: /use <endpoint>\nType /list to see your endpoints."

    # Resolve by name or ID
    info = ctx.endpoint_manager.get_endpoint_by_name(target)
    if info is None:
        return f"Endpoint not found: {target}"

    endpoint_id = info.config.id
    user = ctx.session_store.get_user(ctx.sender_id)
    if user is None:
        return "User not found."

    if not user.is_bound_to(endpoint_id):
        return f"You are not bound to endpoint: {info.config.name or endpoint_id}\nUse /bind {target} first."

    ok = ctx.session_store.set_active_endpoint(ctx.sender_id, endpoint_id)
    if not ok:
        return f"Failed to switch to endpoint: {info.config.name or endpoint_id}"

    name = info.config.name or endpoint_id
    return f"Switched active endpoint to: {name}"


async def _handle_status(ctx: GatewayCommandContext) -> str:
    """Show active endpoint, bound endpoints, and online count."""
    user = ctx.session_store.get_user(ctx.sender_id)
    if user is None:
        return "User not found."

    active = user.active_endpoint
    active_name = active
    if active:
        info = ctx.endpoint_manager.get_endpoint(active)
        if info:
            active_name = info.config.name or active

    bound_count = len(user.bindings)
    online_count = 0
    for b in user.bindings:
        if ctx.endpoint_manager.is_online(b.endpoint_id):
            online_count += 1

    lines = [
        f"Active endpoint: {active_name or 'none'}",
        f"Bound endpoints: {bound_count}",
        f"Online: {online_count}/{bound_count}",
    ]
    return "\n".join(lines)


async def _handle_bind(ctx: GatewayCommandContext) -> str:
    """Bind to an endpoint."""
    target = ctx.args.strip()
    if not target:
        return "Usage: /bind <endpoint>"

    # Resolve by name or ID
    info = ctx.endpoint_manager.get_endpoint_by_name(target)
    if info is None:
        return f"Endpoint not found: {target}"

    endpoint_id = info.config.id
    user = ctx.session_store.get_user(ctx.sender_id)
    if user is None:
        return "User not found."

    if user.is_bound_to(endpoint_id):
        return f"Already bound to: {info.config.name or endpoint_id}"

    ok = ctx.session_store.bind_endpoint(ctx.sender_id, endpoint_id)
    if not ok:
        return f"Failed to bind to endpoint: {info.config.name or endpoint_id}"

    name = info.config.name or endpoint_id
    return f"Bound to endpoint: {name}"


async def _handle_unbind(ctx: GatewayCommandContext) -> str:
    """Unbind from an endpoint."""
    target = ctx.args.strip()
    if not target:
        return "Usage: /unbind <endpoint>"

    info = ctx.endpoint_manager.get_endpoint_by_name(target)
    if info is None:
        return f"Endpoint not found: {target}"

    endpoint_id = info.config.id
    user = ctx.session_store.get_user(ctx.sender_id)
    if user is None:
        return "User not found."

    if not user.is_bound_to(endpoint_id):
        return f"Not bound to: {info.config.name or endpoint_id}"

    ok = ctx.session_store.unbind_endpoint(ctx.sender_id, endpoint_id)
    if not ok:
        return f"Failed to unbind from endpoint: {info.config.name or endpoint_id}"

    name = info.config.name or endpoint_id
    return f"Unbound from endpoint: {name}"


async def _handle_help(ctx: GatewayCommandContext) -> str:
    """Show available commands."""
    lines = [
        "Available commands:",
        "  /list    - List your bound endpoints",
        "  /use <name>  - Switch active endpoint",
        "  /to <name> <msg>  - Send message to a specific endpoint",
        "  /status  - Show your status",
        "  /bind <name>  - Bind to an endpoint",
        "  /unbind <name>  - Unbind from an endpoint",
        "  /help    - Show this help",
    ]
    if ctx.authz.is_admin(ctx.sender_id):
        lines.append("  /admin   - Show system info (admin only)")
    return "\n".join(lines)


async def _handle_admin(ctx: GatewayCommandContext) -> str:
    """Admin-only command: show system info."""
    if not ctx.authz.is_admin(ctx.sender_id):
        return "Permission denied. Admin access required."

    users = ctx.session_store.list_users()
    endpoints = ctx.endpoint_manager.list_endpoints()
    online = ctx.endpoint_manager.get_online_count()
    total = len(endpoints)

    lines = [
        "System Info:",
        f"  Users: {len(users)}",
        f"  Endpoints: {total}",
        f"  Online: {online}/{total}",
        "",
        "Endpoints:",
    ]
    for ep in endpoints:
        status = ep.status.value
        name = ep.config.name or ep.config.id
        lines.append(f"  {name} [{status}] (type={ep.config.type.value})")

    return "\n".join(lines)
