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


class TestRedactBodySensitiveFields:
    """Tests for sensitive field masking in redact_body (P0 coverage)."""

    def test_context_token_redacted(self):
        body = '{"context_token":"secret123","text":"hello"}'
        result = redact_body(body)
        assert "secret123" not in result
        assert '"context_token":"<redacted>"' in result
        assert '"text":"hello"' in result

    def test_bot_token_redacted(self):
        body = '{"bot_token":"my-bot-tok"}'
        result = redact_body(body)
        assert "my-bot-tok" not in result
        assert '"bot_token":"<redacted>"' in result

    def test_token_redacted(self):
        body = '{"token":"bearer-xyz"}'
        result = redact_body(body)
        assert "bearer-xyz" not in result
        assert '"token":"<redacted>"' in result

    def test_authorization_redacted(self):
        body = '{"Authorization":"Bearer zzz"}'
        result = redact_body(body)
        assert "Bearer zzz" not in result
        assert '"Authorization":"<redacted>"' in result

    def test_no_sensitive_fields_unchanged(self):
        body = '{"text":"hello","user":"alice"}'
        assert redact_body(body) == body

    def test_multiple_sensitive_fields(self):
        body = '{"context_token":"a","bot_token":"b","text":"ok"}'
        result = redact_body(body)
        assert "context_token" in result
        assert "bot_token" in result
        assert '"a"' not in result
        assert '"b"' not in result
        assert '"text":"ok"' in result

    def test_redaction_before_truncation(self):
        """Sensitive fields are redacted before length check, so a long secret
        gets replaced with short '<redacted>' and may no longer need truncation."""
        body = '{"context_token":"' + "x" * 300 + '"}'
        result = redact_body(body, max_len=50)
        assert "x" * 10 not in result  # original value must not leak
        assert "<redacted>" in result

    def test_truncation_after_redaction_when_still_long(self):
        """When the body is still long after redaction, it gets truncated."""
        # 200 chars of non-sensitive padding + a sensitive field
        body = '{"data":"' + "a" * 200 + '","token":"secret"}'
        result = redact_body(body, max_len=100)
        assert "secret" not in result
        assert "truncated" in result
