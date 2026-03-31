"""Tests for EndpointManager — endpoint registry and status tracking (Task 3.1)."""

from __future__ import annotations

from wechat_clawbot.gateway.endpoint_manager import EndpointManager
from wechat_clawbot.gateway.types import ChannelType, EndpointConfig, EndpointStatus


def _ep(ep_id: str, name: str = "", ep_type: ChannelType = ChannelType.MCP) -> EndpointConfig:
    """Create an EndpointConfig helper."""
    return EndpointConfig(id=ep_id, name=name or ep_id, type=ep_type)


class TestRegisterUnregister:
    def test_register_endpoint(self):
        mgr = EndpointManager()
        mgr.register(_ep("ep-1", "Endpoint One"))

        info = mgr.get_endpoint("ep-1")
        assert info is not None
        assert info.config.id == "ep-1"
        assert info.config.name == "Endpoint One"
        assert info.status == EndpointStatus.OFFLINE

    def test_register_updates_existing_config(self):
        mgr = EndpointManager()
        mgr.register(_ep("ep-1", "Old Name"))
        mgr.register(_ep("ep-1", "New Name"))

        info = mgr.get_endpoint("ep-1")
        assert info is not None
        assert info.config.name == "New Name"

    def test_register_preserves_runtime_status(self):
        mgr = EndpointManager()
        mgr.register(_ep("ep-1"))
        mgr.set_connected("ep-1", True)

        # Re-register should keep online status
        mgr.register(_ep("ep-1", "Updated"))
        info = mgr.get_endpoint("ep-1")
        assert info is not None
        assert info.status == EndpointStatus.ONLINE

    def test_unregister_endpoint(self):
        mgr = EndpointManager()
        mgr.register(_ep("ep-1"))
        mgr.unregister("ep-1")

        assert mgr.get_endpoint("ep-1") is None

    def test_unregister_nonexistent(self):
        mgr = EndpointManager()
        mgr.unregister("ep-unknown")  # should not raise


class TestQueries:
    def test_get_endpoint_found(self):
        mgr = EndpointManager()
        mgr.register(_ep("ep-1"))
        assert mgr.get_endpoint("ep-1") is not None

    def test_get_endpoint_not_found(self):
        mgr = EndpointManager()
        assert mgr.get_endpoint("ep-1") is None

    def test_get_endpoint_by_name(self):
        mgr = EndpointManager()
        mgr.register(_ep("ep-1", "My Endpoint"))

        info = mgr.get_endpoint_by_name("My Endpoint")
        assert info is not None
        assert info.config.id == "ep-1"

    def test_get_endpoint_by_name_case_insensitive(self):
        mgr = EndpointManager()
        mgr.register(_ep("ep-1", "My Endpoint"))

        info = mgr.get_endpoint_by_name("my endpoint")
        assert info is not None
        assert info.config.id == "ep-1"

    def test_get_endpoint_by_name_falls_back_to_id(self):
        mgr = EndpointManager()
        mgr.register(_ep("ep-1", "Some Name"))

        info = mgr.get_endpoint_by_name("ep-1")
        assert info is not None
        assert info.config.id == "ep-1"

    def test_get_endpoint_by_name_not_found(self):
        mgr = EndpointManager()
        mgr.register(_ep("ep-1", "My Endpoint"))

        assert mgr.get_endpoint_by_name("nonexistent") is None

    def test_list_endpoints(self):
        mgr = EndpointManager()
        mgr.register(_ep("ep-1"))
        mgr.register(_ep("ep-2"))

        eps = mgr.list_endpoints()
        ids = {e.config.id for e in eps}
        assert ids == {"ep-1", "ep-2"}

    def test_list_endpoints_empty(self):
        mgr = EndpointManager()
        assert mgr.list_endpoints() == []

    def test_list_endpoint_ids(self):
        mgr = EndpointManager()
        mgr.register(_ep("ep-1"))
        mgr.register(_ep("ep-2"))

        ids = mgr.list_endpoint_ids()
        assert set(ids) == {"ep-1", "ep-2"}

    def test_is_online_true(self):
        mgr = EndpointManager()
        mgr.register(_ep("ep-1"))
        mgr.set_connected("ep-1", True)
        assert mgr.is_online("ep-1") is True

    def test_is_online_false_when_offline(self):
        mgr = EndpointManager()
        mgr.register(_ep("ep-1"))
        assert mgr.is_online("ep-1") is False

    def test_is_online_false_when_unknown(self):
        mgr = EndpointManager()
        assert mgr.is_online("ep-unknown") is False


class TestStatusUpdates:
    def test_set_connected_true(self):
        mgr = EndpointManager()
        mgr.register(_ep("ep-1"))
        mgr.set_connected("ep-1", True)

        info = mgr.get_endpoint("ep-1")
        assert info is not None
        assert info.status == EndpointStatus.ONLINE
        assert info.connected_at > 0

    def test_set_connected_false(self):
        mgr = EndpointManager()
        mgr.register(_ep("ep-1"))
        mgr.set_connected("ep-1", True)
        mgr.set_connected("ep-1", False)

        info = mgr.get_endpoint("ep-1")
        assert info is not None
        assert info.status == EndpointStatus.OFFLINE

    def test_set_connected_unknown_endpoint(self):
        mgr = EndpointManager()
        # Should not raise
        mgr.set_connected("ep-unknown", True)

    def test_set_error(self):
        mgr = EndpointManager()
        mgr.register(_ep("ep-1"))
        mgr.set_error("ep-1", "connection refused")

        info = mgr.get_endpoint("ep-1")
        assert info is not None
        assert info.status == EndpointStatus.ERROR
        assert info.error_message == "connection refused"

    def test_set_connected_clears_error(self):
        mgr = EndpointManager()
        mgr.register(_ep("ep-1"))
        mgr.set_error("ep-1", "some error")
        mgr.set_connected("ep-1", True)

        info = mgr.get_endpoint("ep-1")
        assert info is not None
        assert info.status == EndpointStatus.ONLINE
        assert info.error_message == ""


class TestFiltering:
    def test_get_endpoints_for_user(self):
        mgr = EndpointManager()
        mgr.register(_ep("ep-1"))
        mgr.register(_ep("ep-2"))
        mgr.register(_ep("ep-3"))

        result = mgr.get_endpoints_for_user(["ep-1", "ep-3"])
        ids = {e.config.id for e in result}
        assert ids == {"ep-1", "ep-3"}

    def test_get_endpoints_for_user_unknown_binding(self):
        mgr = EndpointManager()
        mgr.register(_ep("ep-1"))

        result = mgr.get_endpoints_for_user(["ep-1", "ep-unknown"])
        assert len(result) == 1
        assert result[0].config.id == "ep-1"

    def test_get_endpoints_for_user_empty_bindings(self):
        mgr = EndpointManager()
        mgr.register(_ep("ep-1"))

        result = mgr.get_endpoints_for_user([])
        assert result == []

    def test_get_online_count(self):
        mgr = EndpointManager()
        mgr.register(_ep("ep-1"))
        mgr.register(_ep("ep-2"))
        mgr.register(_ep("ep-3"))

        assert mgr.get_online_count() == 0

        mgr.set_connected("ep-1", True)
        mgr.set_connected("ep-3", True)
        assert mgr.get_online_count() == 2

    def test_get_online_count_empty(self):
        mgr = EndpointManager()
        assert mgr.get_online_count() == 0
