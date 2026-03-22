"""Tests for debug mode toggle."""

import os

from wechat_clawbot.messaging.debug_mode import _reset_for_test, is_debug_mode, toggle_debug_mode


class TestDebugMode:
    def setup_method(self):
        # Ensure test isolation
        os.environ["OPENCLAW_STATE_DIR"] = "/tmp/wechat_clawbot_test_state"
        _reset_for_test()

    def teardown_method(self):
        _reset_for_test()
        os.environ.pop("OPENCLAW_STATE_DIR", None)

    def test_default_off(self):
        assert not is_debug_mode("test-bot")

    def test_toggle_on(self):
        result = toggle_debug_mode("test-bot")
        assert result is True
        assert is_debug_mode("test-bot")

    def test_toggle_off(self):
        toggle_debug_mode("test-bot")  # on
        result = toggle_debug_mode("test-bot")  # off
        assert result is False
        assert not is_debug_mode("test-bot")

    def test_independent_accounts(self):
        toggle_debug_mode("bot-a")
        assert is_debug_mode("bot-a")
        assert not is_debug_mode("bot-b")
