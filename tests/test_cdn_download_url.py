"""Tests for _resolve_cdn_download_url three-way routing."""

from unittest import mock

import pytest

from wechat_clawbot.cdn import download as dl_mod
from wechat_clawbot.cdn.download import _resolve_cdn_download_url

CDN_BASE = "https://cdn.example.com/c2c"


class TestResolveCdnDownloadUrl:
    def test_full_url_takes_priority(self):
        """full_url present -> return it directly, ignore encrypt_query_param."""
        result = _resolve_cdn_download_url(
            "should_be_ignored", CDN_BASE, "test", full_url="https://direct.url/file"
        )
        assert result == "https://direct.url/file"

    def test_full_url_empty_string_falls_back(self):
        """Empty string full_url is falsy -> fallback to encrypt_query_param."""
        result = _resolve_cdn_download_url("qp123", CDN_BASE, "test", full_url="")
        assert "qp123" in result

    def test_full_url_none_with_fallback_enabled(self):
        """full_url=None, ENABLE_CDN_URL_FALLBACK=True -> build from encrypt_query_param."""
        result = _resolve_cdn_download_url("qp_abc", CDN_BASE, "test", full_url=None)
        assert "encrypted_query_param=qp_abc" in result
        assert result.startswith(CDN_BASE)

    def test_fallback_disabled_raises(self):
        """full_url=None, ENABLE_CDN_URL_FALLBACK=False -> RuntimeError."""
        with mock.patch.object(dl_mod, "ENABLE_CDN_URL_FALLBACK", False), pytest.raises(
            RuntimeError, match="full_url is required"
        ):
            _resolve_cdn_download_url("qp", CDN_BASE, "test", full_url=None)

    def test_empty_encrypt_query_param_with_no_full_url_raises(self):
        """full_url=None, encrypt_query_param="" -> RuntimeError (M5 fix)."""
        with pytest.raises(RuntimeError, match="neither full_url nor encrypt_query_param"):
            _resolve_cdn_download_url("", CDN_BASE, "test", full_url=None)

    def test_fallback_disabled_with_full_url_still_works(self):
        """Even if fallback disabled, full_url should work."""
        with mock.patch.object(dl_mod, "ENABLE_CDN_URL_FALLBACK", False):
            result = _resolve_cdn_download_url("", CDN_BASE, "test", full_url="https://ok")
            assert result == "https://ok"
