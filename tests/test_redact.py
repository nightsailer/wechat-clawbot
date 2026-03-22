"""Tests for redact utilities."""

from wechat_clawbot.util.redact import redact_body, redact_token, redact_url, truncate


class TestRedact:
    def test_truncate_short(self):
        assert truncate("hello", 10) == "hello"

    def test_truncate_long(self):
        result = truncate("a" * 50, 10)
        assert result.startswith("a" * 10)
        assert "len=50" in result

    def test_truncate_none(self):
        assert truncate(None, 10) == ""

    def test_redact_token_none(self):
        assert redact_token(None) == "(none)"

    def test_redact_token_short(self):
        assert "****" in redact_token("abc")

    def test_redact_token_normal(self):
        result = redact_token("abcdefghijklmn")
        assert result.startswith("abcdef")
        assert "len=14" in result

    def test_redact_body_empty(self):
        assert redact_body(None) == "(empty)"

    def test_redact_body_short(self):
        assert redact_body("hello") == "hello"

    def test_redact_body_long(self):
        result = redact_body("x" * 300)
        assert "truncated" in result

    def test_redact_url_no_query(self):
        assert redact_url("https://example.com/path") == "https://example.com/path"

    def test_redact_url_with_query(self):
        result = redact_url("https://example.com/path?token=secret")
        assert "secret" not in result
        assert "<redacted>" in result
