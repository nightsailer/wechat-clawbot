"""Tests for session guard (pause/resume)."""

import pytest

from wechat_clawbot.api.session_guard import (
    _reset_for_test,
    assert_session_active,
    get_remaining_pause_ms,
    is_session_paused,
    pause_session,
)


class TestSessionGuard:
    def setup_method(self):
        _reset_for_test()

    def test_not_paused_by_default(self):
        assert not is_session_paused("test-account")
        assert get_remaining_pause_ms("test-account") == 0

    def test_pause_and_check(self):
        pause_session("test-account")
        assert is_session_paused("test-account")
        remaining = get_remaining_pause_ms("test-account")
        assert remaining > 0
        assert remaining <= 60 * 60 * 1000

    def test_assert_active_raises_when_paused(self):
        pause_session("test-account")
        with pytest.raises(RuntimeError, match="session paused"):
            assert_session_active("test-account")

    def test_assert_active_ok_when_not_paused(self):
        assert_session_active("test-account")  # should not raise

    def test_different_accounts_independent(self):
        pause_session("account-a")
        assert is_session_paused("account-a")
        assert not is_session_paused("account-b")
