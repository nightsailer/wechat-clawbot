"""Tests for bridge mode (_MessageQueue, _create_bridge_server, CLI parsing)."""

from __future__ import annotations

from wechat_clawbot.claude_channel.bridge import (
    _build_bridge_tools,
    _create_bridge_server,
    _MessageQueue,
)

# ---------------------------------------------------------------------------
# _MessageQueue
# ---------------------------------------------------------------------------


class TestMessageQueue:
    def test_push_and_drain(self) -> None:
        q = _MessageQueue()
        q.push("alice@im.wechat", "hello")
        q.push("bob@im.wechat", "world")
        msgs = q.drain()
        assert len(msgs) == 2
        assert msgs[0] == {"sender_id": "alice@im.wechat", "text": "hello"}
        assert msgs[1] == {"sender_id": "bob@im.wechat", "text": "world"}

    def test_drain_clears_queue(self) -> None:
        q = _MessageQueue()
        q.push("alice@im.wechat", "hello")
        q.drain()
        assert q.drain() == []
        assert len(q) == 0

    def test_len(self) -> None:
        q = _MessageQueue()
        assert len(q) == 0
        q.push("alice@im.wechat", "hello")
        assert len(q) == 1
        q.push("bob@im.wechat", "world")
        assert len(q) == 2

    def test_bounded_capacity(self) -> None:
        q = _MessageQueue(maxsize=3)
        q.push("a", "1")
        q.push("b", "2")
        q.push("c", "3")
        q.push("d", "4")  # should evict oldest ("a", "1")
        assert len(q) == 3
        msgs = q.drain()
        assert msgs[0]["sender_id"] == "b"
        assert msgs[2]["sender_id"] == "d"

    def test_empty_drain(self) -> None:
        q = _MessageQueue()
        assert q.drain() == []


# ---------------------------------------------------------------------------
# _build_bridge_tools
# ---------------------------------------------------------------------------


class TestBuildBridgeTools:
    def test_includes_base_tools(self) -> None:
        tools = _build_bridge_tools()
        names = {t.name for t in tools}
        assert "wechat_reply" in names
        assert "wechat_send_file" in names
        assert "wechat_typing" in names

    def test_includes_get_messages(self) -> None:
        tools = _build_bridge_tools()
        names = {t.name for t in tools}
        assert "wechat_get_messages" in names

    def test_extra_tool_count(self) -> None:
        from wechat_clawbot.messaging.mcp_defs import TOOLS

        tools = _build_bridge_tools()
        assert len(tools) == len(TOOLS) + 1


# ---------------------------------------------------------------------------
# _create_bridge_server
# ---------------------------------------------------------------------------


class TestCreateBridgeServer:
    def test_returns_server_and_tools(self) -> None:
        q = _MessageQueue()
        server, tools = _create_bridge_server(q)
        assert server is not None
        assert len(tools) > 0

    def test_server_name(self) -> None:
        q = _MessageQueue()
        server, _tools = _create_bridge_server(q)
        assert server.name == "wechat-bridge"

    def test_tools_include_get_messages(self) -> None:
        q = _MessageQueue()
        _server, tools = _create_bridge_server(q)
        names = {t.name for t in tools}
        assert "wechat_get_messages" in names

    def test_tools_include_base_tools(self) -> None:
        q = _MessageQueue()
        _server, tools = _create_bridge_server(q)
        names = {t.name for t in tools}
        assert "wechat_reply" in names
        assert "wechat_send_file" in names
        assert "wechat_typing" in names


# ---------------------------------------------------------------------------
# CLI argument parsing (integration)
# ---------------------------------------------------------------------------


class TestCLIParsing:
    """Test that the CLI correctly parses --gateway/--endpoint flags."""

    def test_help_text_includes_bridge_options(self) -> None:
        """Help text should mention --gateway and --endpoint."""
        import sys
        from io import StringIO

        from wechat_clawbot.claude_channel.cli import _print_help

        old_stdout = sys.stdout
        sys.stdout = StringIO()
        try:
            _print_help()
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        assert "--gateway" in output
        assert "--endpoint" in output
        assert "bridge" in output.lower() or "桥接" in output
