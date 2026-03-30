"""Tests for SDK client library (Phase 4.2)."""

from __future__ import annotations

from wechat_clawbot.sdk.client import ClawBotClient, Message


class TestMessageDataclass:
    """Test Message dataclass creation."""

    def test_required_fields(self) -> None:
        msg = Message(sender_id="user@im.wechat", text="hello")
        assert msg.sender_id == "user@im.wechat"
        assert msg.text == "hello"
        assert msg.context_token is None

    def test_optional_context_token(self) -> None:
        msg = Message(sender_id="user@im.wechat", text="hello", context_token="tok-123")
        assert msg.context_token == "tok-123"

    def test_equality(self) -> None:
        a = Message(sender_id="u1", text="hi")
        b = Message(sender_id="u1", text="hi")
        assert a == b

    def test_inequality(self) -> None:
        a = Message(sender_id="u1", text="hi")
        b = Message(sender_id="u2", text="hi")
        assert a != b


class TestWsUrl:
    """Test ws_url generation (http->ws, https->wss)."""

    def test_http_to_ws(self) -> None:
        client = ClawBotClient(gateway_url="http://localhost:8080", endpoint_id="ep-1")
        assert client.ws_url == "ws://localhost:8080/sdk/ep-1/ws"

    def test_https_to_wss(self) -> None:
        client = ClawBotClient(gateway_url="https://gateway.example.com", endpoint_id="ep-2")
        assert client.ws_url == "wss://gateway.example.com/sdk/ep-2/ws"

    def test_trailing_slash_stripped(self) -> None:
        client = ClawBotClient(gateway_url="http://localhost:8080/", endpoint_id="ep-1")
        assert client.ws_url == "ws://localhost:8080/sdk/ep-1/ws"

    def test_with_path_prefix(self) -> None:
        client = ClawBotClient(gateway_url="http://localhost:8080/api", endpoint_id="ep-1")
        assert client.ws_url == "ws://localhost:8080/api/sdk/ep-1/ws"


class TestClawBotClientAttributes:
    """Test ClawBotClient basic attributes."""

    def test_default_attributes(self) -> None:
        client = ClawBotClient(gateway_url="http://localhost:8080", endpoint_id="ep-1")
        assert client._gateway_url == "http://localhost:8080"
        assert client._endpoint_id == "ep-1"
        assert client._token == ""
        assert client._reconnect is True
        assert client._reconnect_delay == 5.0
        assert client._ws is None
        assert client._closed is False

    def test_custom_attributes(self) -> None:
        client = ClawBotClient(
            gateway_url="https://gw.test.com",
            endpoint_id="my-bot",
            token="secret",
            reconnect=False,
            reconnect_delay=10.0,
        )
        assert client._gateway_url == "https://gw.test.com"
        assert client._endpoint_id == "my-bot"
        assert client._token == "secret"
        assert client._reconnect is False
        assert client._reconnect_delay == 10.0
