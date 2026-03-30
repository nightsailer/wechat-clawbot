"""Tests for gateway core data types (Task 1.8)."""

import time

from wechat_clawbot.gateway.types import (
    ChannelType,
    DeliveryStatus,
    EndpointBinding,
    EndpointSession,
    EndpointStatus,
    RouteType,
    UserRole,
    UserState,
)


class TestEnumValues:
    """Verify enum members and their string values."""

    def test_channel_type_values(self):
        assert ChannelType.MCP == "mcp"
        assert ChannelType.SDK == "sdk"
        assert ChannelType.HTTP == "http"
        assert len(ChannelType) == 3

    def test_endpoint_status_values(self):
        assert EndpointStatus.ONLINE == "online"
        assert EndpointStatus.OFFLINE == "offline"
        assert EndpointStatus.ERROR == "error"
        assert len(EndpointStatus) == 3

    def test_delivery_status_values(self):
        assert DeliveryStatus.PENDING == "pending"
        assert DeliveryStatus.DELIVERED == "delivered"
        assert DeliveryStatus.EXPIRED == "expired"
        assert len(DeliveryStatus) == 3

    def test_user_role_values(self):
        assert UserRole.ADMIN == "admin"
        assert UserRole.USER == "user"
        assert UserRole.GUEST == "guest"
        assert len(UserRole) == 3

    def test_route_type_values(self):
        assert RouteType.ACTIVE_ENDPOINT == "active-endpoint"
        assert RouteType.MENTION == "mention"
        assert RouteType.COMMAND_TO == "command-to"
        assert RouteType.GATEWAY_COMMAND == "gateway-command"
        assert len(RouteType) == 4


class TestEndpointBinding:
    """Test EndpointBinding dataclass defaults."""

    def test_defaults(self):
        before = time.time()
        binding = EndpointBinding(endpoint_id="ep-1")
        after = time.time()

        assert binding.endpoint_id == "ep-1"
        assert before <= binding.bound_at <= after
        assert binding.permissions == ["read", "write"]

    def test_custom_permissions(self):
        binding = EndpointBinding(endpoint_id="ep-2", permissions=["read"])
        assert binding.permissions == ["read"]


class TestEndpointSession:
    """Test EndpointSession dataclass defaults."""

    def test_defaults(self):
        session = EndpointSession()
        assert session.context_token is None
        assert session.last_message_at == 0.0
        assert session.state == {}

    def test_custom_values(self):
        session = EndpointSession(
            context_token="tok-abc",
            last_message_at=1000.0,
            state={"key": "value"},
        )
        assert session.context_token == "tok-abc"
        assert session.last_message_at == 1000.0
        assert session.state == {"key": "value"}


class TestUserState:
    """Test UserState, including is_bound_to() and get_binding()."""

    def test_defaults(self):
        before = time.time()
        user = UserState(user_id="u1")
        after = time.time()

        assert user.user_id == "u1"
        assert user.display_name == ""
        assert user.role == UserRole.GUEST
        assert user.active_endpoint == ""
        assert user.bindings == []
        assert user.endpoint_sessions == {}
        assert user.account_id == ""
        assert before <= user.created_at <= after
        assert before <= user.last_active_at <= after

    def test_is_bound_to_true(self):
        binding = EndpointBinding(endpoint_id="ep-1")
        user = UserState(user_id="u1", bindings=[binding])
        assert user.is_bound_to("ep-1") is True

    def test_is_bound_to_false(self):
        user = UserState(user_id="u1")
        assert user.is_bound_to("ep-1") is False

    def test_is_bound_to_false_with_other_bindings(self):
        binding = EndpointBinding(endpoint_id="ep-2")
        user = UserState(user_id="u1", bindings=[binding])
        assert user.is_bound_to("ep-1") is False

    def test_get_binding_found(self):
        binding = EndpointBinding(endpoint_id="ep-1")
        user = UserState(user_id="u1", bindings=[binding])
        result = user.get_binding("ep-1")
        assert result is binding

    def test_get_binding_not_found(self):
        user = UserState(user_id="u1")
        assert user.get_binding("ep-1") is None

    def test_get_binding_returns_correct_one(self):
        b1 = EndpointBinding(endpoint_id="ep-1")
        b2 = EndpointBinding(endpoint_id="ep-2")
        user = UserState(user_id="u1", bindings=[b1, b2])
        assert user.get_binding("ep-2") is b2
