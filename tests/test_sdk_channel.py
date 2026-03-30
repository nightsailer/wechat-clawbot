"""Tests for SDKChannel (Phase 4.1)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.routing import WebSocketRoute

from wechat_clawbot.gateway.channels.sdk_channel import SDKChannel


@pytest.fixture
def channel() -> SDKChannel:
    """Create an SDKChannel with a mock reply callback."""
    return SDKChannel(on_reply=AsyncMock())


class TestGetRoutes:
    """Test SDKChannel.get_routes()."""

    def test_returns_websocket_route(self, channel: SDKChannel) -> None:
        routes = channel.get_routes()
        assert len(routes) == 1
        assert isinstance(routes[0], WebSocketRoute)

    def test_route_path(self, channel: SDKChannel) -> None:
        routes = channel.get_routes()
        assert routes[0].path == "/sdk/{endpoint_id}/ws"


class TestIsEndpointConnected:
    """Test is_endpoint_connected before/after mock connection."""

    def test_not_connected_by_default(self, channel: SDKChannel) -> None:
        assert channel.is_endpoint_connected("ep-1") is False

    def test_connected_after_adding(self, channel: SDKChannel) -> None:
        # Simulate a connection by injecting into _connections
        channel._connections["ep-1"] = MagicMock()
        assert channel.is_endpoint_connected("ep-1") is True

    def test_not_connected_after_removing(self, channel: SDKChannel) -> None:
        channel._connections["ep-1"] = MagicMock()
        del channel._connections["ep-1"]
        assert channel.is_endpoint_connected("ep-1") is False


class TestGetConnectedEndpoints:
    """Test get_connected_endpoints."""

    def test_empty_when_no_connections(self, channel: SDKChannel) -> None:
        assert channel.get_connected_endpoints() == []

    def test_returns_connected_ids(self, channel: SDKChannel) -> None:
        channel._connections["ep-a"] = MagicMock()
        channel._connections["ep-b"] = MagicMock()
        result = channel.get_connected_endpoints()
        assert result == ["ep-a", "ep-b"]

    def test_returns_sorted(self, channel: SDKChannel) -> None:
        channel._connections["ep-z"] = MagicMock()
        channel._connections["ep-a"] = MagicMock()
        result = channel.get_connected_endpoints()
        assert result == ["ep-a", "ep-z"]


class TestDeliverMessage:
    """Test deliver_message returns False when not connected."""

    @pytest.mark.asyncio
    async def test_returns_false_when_not_connected(self, channel: SDKChannel) -> None:
        result = await channel.deliver_message("ep-1", "user@im.wechat", "hello")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_when_connected(self, channel: SDKChannel) -> None:
        mock_ws = AsyncMock()
        channel._connections["ep-1"] = mock_ws
        result = await channel.deliver_message("ep-1", "user@im.wechat", "hello")
        assert result is True
        mock_ws.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_on_send_error(self, channel: SDKChannel) -> None:
        mock_ws = AsyncMock()
        mock_ws.send_text.side_effect = RuntimeError("connection lost")
        channel._connections["ep-1"] = mock_ws
        result = await channel.deliver_message("ep-1", "user@im.wechat", "hello")
        assert result is False


class TestStartStop:
    """Test start/stop lifecycle methods."""

    @pytest.mark.asyncio
    async def test_start_is_noop(self, channel: SDKChannel) -> None:
        await channel.start()  # Should not raise

    @pytest.mark.asyncio
    async def test_stop_clears_connections(self, channel: SDKChannel) -> None:
        mock_ws = AsyncMock()
        channel._connections["ep-1"] = mock_ws
        await channel.stop()
        assert channel._connections == {}
        mock_ws.close.assert_called_once()


class TestSendReply:
    """Test send_reply (no-op for SDK channel)."""

    @pytest.mark.asyncio
    async def test_send_reply_is_noop(self, channel: SDKChannel) -> None:
        await channel.send_reply("ep-1", "user@im.wechat", "hello")
