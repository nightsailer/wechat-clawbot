"""Tests for HTTPChannel (Phase 6.1)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from starlette.routing import Route
from starlette.testclient import TestClient

from wechat_clawbot.gateway.channels.http_channel import HTTPChannel


def _test_client() -> httpx.AsyncClient:
    """Create an httpx client that ignores proxy env vars."""
    return httpx.AsyncClient(timeout=30.0, trust_env=False)


@pytest.fixture
def on_reply() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def channel(on_reply: AsyncMock) -> HTTPChannel:
    """Create an HTTPChannel with a mock reply callback."""
    return HTTPChannel(on_reply=on_reply)


# ---------------------------------------------------------------------------
# get_routes
# ---------------------------------------------------------------------------


class TestGetRoutes:
    def test_returns_route(self, channel: HTTPChannel) -> None:
        routes = channel.get_routes()
        assert len(routes) == 1
        assert isinstance(routes[0], Route)

    def test_route_path(self, channel: HTTPChannel) -> None:
        routes = channel.get_routes()
        assert "/http/{endpoint_id}/callback" in routes[0].path


# ---------------------------------------------------------------------------
# register / unregister / connectivity
# ---------------------------------------------------------------------------


class TestEndpointRegistration:
    def test_register_makes_connected(self, channel: HTTPChannel) -> None:
        channel.register_endpoint("ep-1", url="http://example.com/hook")
        assert channel.is_endpoint_connected("ep-1") is True

    def test_unregister_makes_disconnected(self, channel: HTTPChannel) -> None:
        channel.register_endpoint("ep-1", url="http://example.com/hook")
        channel.unregister_endpoint("ep-1")
        assert channel.is_endpoint_connected("ep-1") is False

    def test_not_connected_by_default(self, channel: HTTPChannel) -> None:
        assert channel.is_endpoint_connected("ep-1") is False

    def test_register_without_url_not_connected(self, channel: HTTPChannel) -> None:
        channel.register_endpoint("ep-1", url="")
        assert channel.is_endpoint_connected("ep-1") is False

    def test_get_connected_endpoints(self, channel: HTTPChannel) -> None:
        channel.register_endpoint("ep-b", url="http://b.example.com/hook")
        channel.register_endpoint("ep-a", url="http://a.example.com/hook")
        channel.register_endpoint("ep-c", url="")
        result = channel.get_connected_endpoints()
        assert result == ["ep-a", "ep-b"]  # sorted, excludes ep-c

    def test_get_connected_endpoints_empty(self, channel: HTTPChannel) -> None:
        assert channel.get_connected_endpoints() == []


# ---------------------------------------------------------------------------
# deliver_message
# ---------------------------------------------------------------------------


class TestDeliverMessage:
    @pytest.mark.asyncio
    async def test_returns_false_when_not_registered(self, channel: HTTPChannel) -> None:
        await channel.start(client=_test_client())
        result = await channel.deliver_message("ep-1", "user@im.wechat", "hello")
        assert result is False
        await channel.stop()

    @pytest.mark.asyncio
    async def test_returns_false_when_no_url(self, channel: HTTPChannel) -> None:
        await channel.start(client=_test_client())
        channel.register_endpoint("ep-1", url="")
        result = await channel.deliver_message("ep-1", "user@im.wechat", "hello")
        assert result is False
        await channel.stop()

    @pytest.mark.asyncio
    async def test_returns_false_when_client_not_started(self, channel: HTTPChannel) -> None:
        channel.register_endpoint("ep-1", url="http://example.com/hook")
        result = await channel.deliver_message("ep-1", "user@im.wechat", "hello")
        assert result is False

    @pytest.mark.asyncio
    @respx.mock
    async def test_successful_delivery(self, channel: HTTPChannel, on_reply: AsyncMock) -> None:
        respx.post("http://example.com/hook").mock(
            return_value=httpx.Response(200, json={"status": "ok"})
        )
        await channel.start(client=_test_client())
        channel.register_endpoint("ep-1", url="http://example.com/hook")
        result = await channel.deliver_message("ep-1", "user@im.wechat", "hello")
        assert result is True
        on_reply.assert_not_called()  # no reply in response
        await channel.stop()

    @pytest.mark.asyncio
    @respx.mock
    async def test_delivery_with_reply_in_response(
        self, channel: HTTPChannel, on_reply: AsyncMock
    ) -> None:
        respx.post("http://example.com/hook").mock(
            return_value=httpx.Response(200, json={"reply": "got it!"})
        )
        await channel.start(client=_test_client())
        channel.register_endpoint("ep-1", url="http://example.com/hook")
        result = await channel.deliver_message("ep-1", "user@im.wechat", "hello")
        assert result is True
        on_reply.assert_called_once_with("ep-1", "user@im.wechat", "got it!")
        await channel.stop()

    @pytest.mark.asyncio
    @respx.mock
    async def test_delivery_with_text_reply_in_response(
        self, channel: HTTPChannel, on_reply: AsyncMock
    ) -> None:
        respx.post("http://example.com/hook").mock(
            return_value=httpx.Response(200, json={"text": "response via text"})
        )
        await channel.start(client=_test_client())
        channel.register_endpoint("ep-1", url="http://example.com/hook")
        result = await channel.deliver_message("ep-1", "user@im.wechat", "hello")
        assert result is True
        on_reply.assert_called_once_with("ep-1", "user@im.wechat", "response via text")
        await channel.stop()

    @pytest.mark.asyncio
    @respx.mock
    async def test_delivery_with_api_key(self, channel: HTTPChannel) -> None:
        route = respx.post("http://example.com/hook")
        route.mock(return_value=httpx.Response(200, json={"status": "ok"}))
        await channel.start(client=_test_client())
        channel.register_endpoint("ep-1", url="http://example.com/hook", api_key="secret123")
        await channel.deliver_message("ep-1", "user@im.wechat", "hello")
        assert route.calls[0].request.headers["Authorization"] == "Bearer secret123"
        await channel.stop()

    @pytest.mark.asyncio
    @respx.mock
    async def test_delivery_failure_non_200(self, channel: HTTPChannel) -> None:
        respx.post("http://example.com/hook").mock(return_value=httpx.Response(500, text="error"))
        await channel.start(client=_test_client())
        channel.register_endpoint("ep-1", url="http://example.com/hook")
        result = await channel.deliver_message("ep-1", "user@im.wechat", "hello")
        assert result is False
        await channel.stop()

    @pytest.mark.asyncio
    @respx.mock
    async def test_delivery_failure_exception(self, channel: HTTPChannel) -> None:
        respx.post("http://example.com/hook").mock(side_effect=httpx.ConnectError("refused"))
        await channel.start(client=_test_client())
        channel.register_endpoint("ep-1", url="http://example.com/hook")
        result = await channel.deliver_message("ep-1", "user@im.wechat", "hello")
        assert result is False
        await channel.stop()


# ---------------------------------------------------------------------------
# callback handler
# ---------------------------------------------------------------------------


class TestCallback:
    def test_callback_route(self, channel: HTTPChannel, on_reply: AsyncMock) -> None:
        """Test the callback endpoint via Starlette test client."""
        from starlette.applications import Starlette

        # Must register endpoint so callback handler finds it
        channel.register_endpoint("ep-1", "http://example.com/hook")
        app = Starlette(routes=channel.get_routes())
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/http/ep-1/callback",
            json={"sender_id": "user@im.wechat", "text": "hi from webhook"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        on_reply.assert_called_once_with("ep-1", "user@im.wechat", "hi from webhook")

    def test_callback_unregistered_endpoint(self, channel: HTTPChannel) -> None:
        """Callback to unregistered endpoint returns 404."""
        from starlette.applications import Starlette

        app = Starlette(routes=channel.get_routes())
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/http/unknown/callback", json={"sender_id": "u", "text": "t"})
        assert resp.status_code == 404

    def test_callback_ignores_empty_fields(self, channel: HTTPChannel, on_reply: AsyncMock) -> None:
        from starlette.applications import Starlette

        channel.register_endpoint("ep-1", "http://example.com/hook")
        app = Starlette(routes=channel.get_routes())
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/http/ep-1/callback", json={"sender_id": "", "text": ""})
        assert resp.status_code == 200
        on_reply.assert_not_called()


# ---------------------------------------------------------------------------
# start / stop lifecycle
# ---------------------------------------------------------------------------


class TestStartStop:
    @pytest.mark.asyncio
    async def test_start_creates_client(self, channel: HTTPChannel) -> None:
        assert channel._client is None
        await channel.start(client=_test_client())
        assert channel._client is not None
        await channel.stop()

    @pytest.mark.asyncio
    async def test_stop_closes_client(self, channel: HTTPChannel) -> None:
        await channel.start(client=_test_client())
        await channel.stop()
        assert channel._client is None

    @pytest.mark.asyncio
    async def test_stop_without_start(self, channel: HTTPChannel) -> None:
        await channel.stop()  # Should not raise


# ---------------------------------------------------------------------------
# send_reply (no-op)
# ---------------------------------------------------------------------------


class TestSendReply:
    @pytest.mark.asyncio
    async def test_send_reply_is_noop(self, channel: HTTPChannel) -> None:
        await channel.send_reply("ep-1", "user@im.wechat", "hello")
