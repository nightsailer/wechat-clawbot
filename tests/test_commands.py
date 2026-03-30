"""Tests for gateway command handlers (Task 3.3)."""

from __future__ import annotations

import pytest

from wechat_clawbot.gateway.auth import AuthZModule
from wechat_clawbot.gateway.commands import GatewayCommandContext, handle_command
from wechat_clawbot.gateway.config import AuthorizationConfig
from wechat_clawbot.gateway.endpoint_manager import EndpointManager
from wechat_clawbot.gateway.session import SessionStore
from wechat_clawbot.gateway.types import ChannelType, EndpointConfig, UserRole


def _make_ctx(
    tmp_path,
    command: str,
    args: str = "",
    sender_id: str = "user-1",
    *,
    admins: list[str] | None = None,
    endpoints: list[EndpointConfig] | None = None,
    user_endpoints: list[str] | None = None,
    create_user: bool = True,
    user_role: UserRole = UserRole.USER,
) -> GatewayCommandContext:
    """Build a GatewayCommandContext with test fixtures."""
    ep_mgr = EndpointManager()
    if endpoints is None:
        endpoints = [
            EndpointConfig(id="ep-1", name="Alpha", type=ChannelType.MCP),
            EndpointConfig(id="ep-2", name="Beta", type=ChannelType.MCP),
        ]
    for ep in endpoints:
        ep_mgr.register(ep)

    session = SessionStore(tmp_path / "users")
    if create_user:
        bound = user_endpoints if user_endpoints is not None else ["ep-1", "ep-2"]
        session.create_user(sender_id, role=user_role, default_endpoints=bound)

    authz_config = AuthorizationConfig(
        mode="open",
        admins=admins or [],
        default_endpoints=["ep-1"],
    )
    authz = AuthZModule(authz_config)

    return GatewayCommandContext(
        sender_id=sender_id,
        account_id="acc-1",
        command=command,
        args=args,
        session_store=session,
        endpoint_manager=ep_mgr,
        authz=authz,
    )


class TestListCommand:
    @pytest.mark.anyio
    async def test_list_shows_endpoints(self, tmp_path):
        ctx = _make_ctx(tmp_path, "list")
        result = await handle_command(ctx)

        assert "Alpha" in result
        assert "Beta" in result

    @pytest.mark.anyio
    async def test_list_shows_active_marker(self, tmp_path):
        ctx = _make_ctx(tmp_path, "list")
        result = await handle_command(ctx)

        assert "(active)" in result

    @pytest.mark.anyio
    async def test_list_shows_online_status(self, tmp_path):
        ctx = _make_ctx(tmp_path, "list")
        ctx.endpoint_manager.set_connected("ep-1", True)
        result = await handle_command(ctx)

        assert "[online]" in result
        assert "[offline]" in result

    @pytest.mark.anyio
    async def test_list_no_bindings(self, tmp_path):
        ctx = _make_ctx(tmp_path, "list", user_endpoints=[])
        result = await handle_command(ctx)

        assert "no bound endpoints" in result.lower()

    @pytest.mark.anyio
    async def test_list_user_not_found(self, tmp_path):
        ctx = _make_ctx(tmp_path, "list", sender_id="ghost", create_user=False)
        result = await handle_command(ctx)

        assert "not found" in result.lower()


class TestUseCommand:
    @pytest.mark.anyio
    async def test_use_switches_endpoint(self, tmp_path):
        ctx = _make_ctx(tmp_path, "use", args="Beta")
        result = await handle_command(ctx)

        assert "Beta" in result
        assert "switched" in result.lower()
        assert ctx.session_store.get_active_endpoint("user-1") == "ep-2"

    @pytest.mark.anyio
    async def test_use_by_id(self, tmp_path):
        ctx = _make_ctx(tmp_path, "use", args="ep-2")
        result = await handle_command(ctx)

        assert "switched" in result.lower()

    @pytest.mark.anyio
    async def test_use_unknown_endpoint(self, tmp_path):
        ctx = _make_ctx(tmp_path, "use", args="Unknown")
        result = await handle_command(ctx)

        assert "not found" in result.lower()

    @pytest.mark.anyio
    async def test_use_not_bound(self, tmp_path):
        ctx = _make_ctx(tmp_path, "use", args="Alpha", user_endpoints=["ep-2"])
        result = await handle_command(ctx)

        assert "not bound" in result.lower()

    @pytest.mark.anyio
    async def test_use_no_args(self, tmp_path):
        ctx = _make_ctx(tmp_path, "use", args="")
        result = await handle_command(ctx)

        assert "usage" in result.lower()


class TestStatusCommand:
    @pytest.mark.anyio
    async def test_status_shows_info(self, tmp_path):
        ctx = _make_ctx(tmp_path, "status")
        ctx.endpoint_manager.set_connected("ep-1", True)
        result = await handle_command(ctx)

        assert "Alpha" in result
        assert "2" in result  # bound count
        assert "1/2" in result  # online/total

    @pytest.mark.anyio
    async def test_status_user_not_found(self, tmp_path):
        ctx = _make_ctx(tmp_path, "status", sender_id="ghost", create_user=False)
        result = await handle_command(ctx)

        assert "not found" in result.lower()


class TestBindCommand:
    @pytest.mark.anyio
    async def test_bind_new_endpoint(self, tmp_path):
        ctx = _make_ctx(tmp_path, "bind", args="Beta", user_endpoints=["ep-1"])
        result = await handle_command(ctx)

        assert "bound" in result.lower()
        assert "Beta" in result
        user = ctx.session_store.get_user("user-1")
        assert user is not None
        assert user.is_bound_to("ep-2")

    @pytest.mark.anyio
    async def test_bind_already_bound(self, tmp_path):
        ctx = _make_ctx(tmp_path, "bind", args="Alpha")
        result = await handle_command(ctx)

        assert "already" in result.lower()

    @pytest.mark.anyio
    async def test_bind_unknown_endpoint(self, tmp_path):
        ctx = _make_ctx(tmp_path, "bind", args="Unknown")
        result = await handle_command(ctx)

        assert "not found" in result.lower()

    @pytest.mark.anyio
    async def test_bind_no_args(self, tmp_path):
        ctx = _make_ctx(tmp_path, "bind", args="")
        result = await handle_command(ctx)

        assert "usage" in result.lower()


class TestUnbindCommand:
    @pytest.mark.anyio
    async def test_unbind_endpoint(self, tmp_path):
        ctx = _make_ctx(tmp_path, "unbind", args="Beta")
        result = await handle_command(ctx)

        assert "unbound" in result.lower()
        user = ctx.session_store.get_user("user-1")
        assert user is not None
        assert not user.is_bound_to("ep-2")

    @pytest.mark.anyio
    async def test_unbind_not_bound(self, tmp_path):
        ctx = _make_ctx(tmp_path, "unbind", args="Beta", user_endpoints=["ep-1"])
        result = await handle_command(ctx)

        assert "not bound" in result.lower()

    @pytest.mark.anyio
    async def test_unbind_unknown_endpoint(self, tmp_path):
        ctx = _make_ctx(tmp_path, "unbind", args="Unknown")
        result = await handle_command(ctx)

        assert "not found" in result.lower()

    @pytest.mark.anyio
    async def test_unbind_no_args(self, tmp_path):
        ctx = _make_ctx(tmp_path, "unbind", args="")
        result = await handle_command(ctx)

        assert "usage" in result.lower()


class TestHelpCommand:
    @pytest.mark.anyio
    async def test_help_shows_all_commands(self, tmp_path):
        ctx = _make_ctx(tmp_path, "help")
        result = await handle_command(ctx)

        assert "/list" in result
        assert "/use" in result
        assert "/to" in result
        assert "/status" in result
        assert "/bind" in result
        assert "/unbind" in result
        assert "/help" in result

    @pytest.mark.anyio
    async def test_help_shows_admin_for_admins(self, tmp_path):
        ctx = _make_ctx(tmp_path, "help", admins=["user-1"])
        result = await handle_command(ctx)

        assert "/admin" in result

    @pytest.mark.anyio
    async def test_help_hides_admin_for_regular_users(self, tmp_path):
        ctx = _make_ctx(tmp_path, "help", admins=[])
        result = await handle_command(ctx)

        assert "/admin" not in result


class TestAdminCommand:
    @pytest.mark.anyio
    async def test_admin_shows_system_info(self, tmp_path):
        ctx = _make_ctx(tmp_path, "admin", admins=["user-1"])
        ctx.endpoint_manager.set_connected("ep-1", True)
        result = await handle_command(ctx)

        assert "System Info" in result
        assert "Users:" in result
        assert "Endpoints:" in result

    @pytest.mark.anyio
    async def test_admin_denied_for_non_admin(self, tmp_path):
        ctx = _make_ctx(tmp_path, "admin", admins=[])
        result = await handle_command(ctx)

        assert "permission denied" in result.lower()


class TestUnknownCommand:
    @pytest.mark.anyio
    async def test_unknown_command(self, tmp_path):
        ctx = _make_ctx(tmp_path, "foobar")
        result = await handle_command(ctx)

        assert "unknown command" in result.lower()
        assert "/help" in result.lower()
