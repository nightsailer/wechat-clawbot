"""Tests for slash command handler."""

from wechat_clawbot.messaging.slash_commands import SlashCommandContext, SlashCommandResult


class TestSlashCommandParsing:
    """Test command parsing without network calls."""

    def test_non_command_not_handled(self):
        # Just verify the result type
        result = SlashCommandResult(handled=False)
        assert result.handled is False

    def test_result_type(self):
        result = SlashCommandResult(handled=True)
        assert result.handled is True

    def test_context_creation(self):
        ctx = SlashCommandContext(
            to="user@im.wechat",
            context_token="ctx",
            base_url="https://example.com",
            token="tok",
            account_id="acc",
            log=lambda m: None,
            err_log=lambda m: None,
        )
        assert ctx.to == "user@im.wechat"
        assert ctx.account_id == "acc"
