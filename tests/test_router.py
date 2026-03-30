"""Tests for Router — message routing engine (Task 3.2)."""

from __future__ import annotations

from wechat_clawbot.gateway.config import RoutingConfig
from wechat_clawbot.gateway.endpoint_manager import EndpointManager
from wechat_clawbot.gateway.router import Router
from wechat_clawbot.gateway.session import SessionStore
from wechat_clawbot.gateway.types import ChannelType, EndpointConfig, RouteType


def _setup(
    tmp_path,
    endpoints: list[EndpointConfig] | None = None,
    default_user: bool = True,
    user_endpoints: list[str] | None = None,
    mention_prefix: str = "@",
    gateway_commands: list[str] | None = None,
) -> tuple[Router, SessionStore, EndpointManager]:
    """Create a Router with test fixtures."""
    ep_mgr = EndpointManager()
    if endpoints is None:
        endpoints = [
            EndpointConfig(id="ep-1", name="Alpha", type=ChannelType.MCP),
            EndpointConfig(id="ep-2", name="Beta", type=ChannelType.MCP),
        ]
    for ep in endpoints:
        ep_mgr.register(ep)

    session = SessionStore(tmp_path / "users")
    if default_user:
        bound = user_endpoints if user_endpoints is not None else ["ep-1", "ep-2"]
        session.create_user("user-1", default_endpoints=bound)

    config = RoutingConfig(
        mention_prefix=mention_prefix,
        gateway_commands=gateway_commands or ["/"],
    )
    router = Router(config=config, session_store=session, endpoint_manager=ep_mgr)
    return router, session, ep_mgr


class TestActiveEndpointRouting:
    def test_plain_text_routes_to_active(self, tmp_path):
        router, _, _ = _setup(tmp_path)
        result = router.resolve("user-1", "hello world")

        assert result.type == RouteType.ACTIVE_ENDPOINT
        assert result.endpoint_id == "ep-1"
        assert result.cleaned_text == "hello world"
        assert result.error == ""

    def test_no_active_endpoint(self, tmp_path):
        router, session, _ = _setup(tmp_path, user_endpoints=[])
        # User has no bindings, hence no active endpoint
        result = router.resolve("user-1", "hello")

        assert result.type == RouteType.ACTIVE_ENDPOINT
        assert result.endpoint_id == ""
        assert result.error == "No active endpoint"

    def test_unknown_user_no_active(self, tmp_path):
        router, _, _ = _setup(tmp_path, default_user=False)
        result = router.resolve("unknown-user", "hello")

        assert result.type == RouteType.ACTIVE_ENDPOINT
        assert result.error == "No active endpoint"

    def test_whitespace_preserved_in_text(self, tmp_path):
        router, _, _ = _setup(tmp_path)
        result = router.resolve("user-1", "  hello  ")
        # Text gets stripped
        assert result.cleaned_text == "hello"


class TestGatewayCommands:
    def test_list_command(self, tmp_path):
        router, _, _ = _setup(tmp_path)
        result = router.resolve("user-1", "/list")

        assert result.type == RouteType.GATEWAY_COMMAND
        assert result.command == "list"
        assert result.command_args == ""

    def test_help_command(self, tmp_path):
        router, _, _ = _setup(tmp_path)
        result = router.resolve("user-1", "/help")

        assert result.type == RouteType.GATEWAY_COMMAND
        assert result.command == "help"

    def test_use_command_with_args(self, tmp_path):
        router, _, _ = _setup(tmp_path)
        result = router.resolve("user-1", "/use Beta")

        assert result.type == RouteType.GATEWAY_COMMAND
        assert result.command == "use"
        assert result.command_args == "Beta"

    def test_status_command(self, tmp_path):
        router, _, _ = _setup(tmp_path)
        result = router.resolve("user-1", "/status")

        assert result.type == RouteType.GATEWAY_COMMAND
        assert result.command == "status"

    def test_bind_command(self, tmp_path):
        router, _, _ = _setup(tmp_path)
        result = router.resolve("user-1", "/bind ep-3")

        assert result.type == RouteType.GATEWAY_COMMAND
        assert result.command == "bind"
        assert result.command_args == "ep-3"

    def test_unbind_command(self, tmp_path):
        router, _, _ = _setup(tmp_path)
        result = router.resolve("user-1", "/unbind ep-1")

        assert result.type == RouteType.GATEWAY_COMMAND
        assert result.command == "unbind"
        assert result.command_args == "ep-1"

    def test_admin_command(self, tmp_path):
        router, _, _ = _setup(tmp_path)
        result = router.resolve("user-1", "/admin")

        assert result.type == RouteType.GATEWAY_COMMAND
        assert result.command == "admin"

    def test_unknown_slash_command_routes_to_active(self, tmp_path):
        """An unknown /command should not be treated as a gateway command."""
        router, _, _ = _setup(tmp_path)
        result = router.resolve("user-1", "/unknown")

        assert result.type == RouteType.ACTIVE_ENDPOINT
        assert result.endpoint_id == "ep-1"
        assert result.cleaned_text == "/unknown"

    def test_command_case_insensitive(self, tmp_path):
        router, _, _ = _setup(tmp_path)
        result = router.resolve("user-1", "/LIST")

        assert result.type == RouteType.GATEWAY_COMMAND
        assert result.command == "list"

    def test_command_with_extra_spaces(self, tmp_path):
        router, _, _ = _setup(tmp_path)
        result = router.resolve("user-1", "/use   Alpha")

        assert result.type == RouteType.GATEWAY_COMMAND
        assert result.command == "use"
        assert result.command_args == "Alpha"

    def test_bare_slash_routes_to_active(self, tmp_path):
        """A bare '/' without a command should route to active endpoint."""
        router, _, _ = _setup(tmp_path)
        result = router.resolve("user-1", "/")

        assert result.type == RouteType.ACTIVE_ENDPOINT


class TestCommandTo:
    def test_to_command_routes_to_endpoint(self, tmp_path):
        router, _, _ = _setup(tmp_path)
        result = router.resolve("user-1", "/to Alpha hello there")

        assert result.type == RouteType.COMMAND_TO
        assert result.endpoint_id == "ep-1"
        assert result.cleaned_text == "hello there"

    def test_to_command_by_id(self, tmp_path):
        router, _, _ = _setup(tmp_path)
        result = router.resolve("user-1", "/to ep-2 test message")

        assert result.type == RouteType.COMMAND_TO
        assert result.endpoint_id == "ep-2"
        assert result.cleaned_text == "test message"

    def test_to_command_unknown_endpoint(self, tmp_path):
        router, _, _ = _setup(tmp_path)
        result = router.resolve("user-1", "/to NonExistent hello")

        assert result.type == RouteType.GATEWAY_COMMAND
        assert result.command == "to"
        assert "not found" in result.error.lower()

    def test_to_command_no_args(self, tmp_path):
        router, _, _ = _setup(tmp_path)
        result = router.resolve("user-1", "/to")

        assert result.type == RouteType.GATEWAY_COMMAND
        assert result.command == "to"
        assert "usage" in result.error.lower()

    def test_to_command_no_message(self, tmp_path):
        router, _, _ = _setup(tmp_path)
        result = router.resolve("user-1", "/to Alpha")

        assert result.type == RouteType.GATEWAY_COMMAND
        assert result.command == "to"
        assert "usage" in result.error.lower()


class TestMentionRouting:
    def test_mention_routes_to_endpoint(self, tmp_path):
        router, _, _ = _setup(tmp_path)
        result = router.resolve("user-1", "@Alpha hello there")

        assert result.type == RouteType.MENTION
        assert result.endpoint_id == "ep-1"
        assert result.cleaned_text == "hello there"

    def test_mention_by_id(self, tmp_path):
        router, _, _ = _setup(tmp_path)
        result = router.resolve("user-1", "@ep-2 test message")

        assert result.type == RouteType.MENTION
        assert result.endpoint_id == "ep-2"
        assert result.cleaned_text == "test message"

    def test_mention_unknown_endpoint_falls_through(self, tmp_path):
        """Unknown @name should fall through to active endpoint routing."""
        router, _, _ = _setup(tmp_path)
        result = router.resolve("user-1", "@NonExistent hello")

        assert result.type == RouteType.ACTIVE_ENDPOINT
        assert result.endpoint_id == "ep-1"
        assert result.cleaned_text == "@NonExistent hello"

    def test_mention_no_message(self, tmp_path):
        router, _, _ = _setup(tmp_path)
        result = router.resolve("user-1", "@Alpha")

        assert result.type == RouteType.MENTION
        assert result.endpoint_id == "ep-1"
        assert result.cleaned_text == ""

    def test_bare_at_sign_routes_to_active(self, tmp_path):
        """A bare '@' should route to active endpoint."""
        router, _, _ = _setup(tmp_path)
        result = router.resolve("user-1", "@")

        assert result.type == RouteType.ACTIVE_ENDPOINT

    def test_custom_mention_prefix(self, tmp_path):
        router, _, _ = _setup(tmp_path, mention_prefix="#")
        result = router.resolve("user-1", "#Alpha hello")

        assert result.type == RouteType.MENTION
        assert result.endpoint_id == "ep-1"
        assert result.cleaned_text == "hello"


class TestPriorityOrder:
    def test_command_takes_priority_over_mention(self, tmp_path):
        """If text matches both command and mention prefix, command wins."""
        # This tests the case where a gateway command prefix is checked first
        router, _, _ = _setup(tmp_path)
        result = router.resolve("user-1", "/list")

        assert result.type == RouteType.GATEWAY_COMMAND

    def test_mention_takes_priority_over_active(self, tmp_path):
        router, _, _ = _setup(tmp_path)
        result = router.resolve("user-1", "@Beta hello")

        assert result.type == RouteType.MENTION
        assert result.endpoint_id == "ep-2"
