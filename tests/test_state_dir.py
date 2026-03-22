"""Tests for state directory resolution."""

from pathlib import Path

from wechat_clawbot.storage.state_dir import resolve_state_dir


class TestStateDir:
    def test_default(self, monkeypatch):
        monkeypatch.delenv("OPENCLAW_STATE_DIR", raising=False)
        monkeypatch.delenv("CLAWDBOT_STATE_DIR", raising=False)
        result = resolve_state_dir()
        assert result == Path.home() / ".openclaw"

    def test_openclaw_env(self, monkeypatch):
        monkeypatch.setenv("OPENCLAW_STATE_DIR", "/custom/state")
        result = resolve_state_dir()
        assert result == Path("/custom/state")

    def test_clawdbot_fallback(self, monkeypatch):
        monkeypatch.delenv("OPENCLAW_STATE_DIR", raising=False)
        monkeypatch.setenv("CLAWDBOT_STATE_DIR", "/legacy/state")
        result = resolve_state_dir()
        assert result == Path("/legacy/state")

    def test_openclaw_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("OPENCLAW_STATE_DIR", "/primary")
        monkeypatch.setenv("CLAWDBOT_STATE_DIR", "/fallback")
        result = resolve_state_dir()
        assert result == Path("/primary")
