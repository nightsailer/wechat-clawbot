"""Tests for CDN URL builders."""

from wechat_clawbot.cdn.cdn_url import build_cdn_download_url, build_cdn_upload_url


class TestCdnUrl:
    def test_download_url(self):
        url = build_cdn_download_url("abc123", "https://cdn.example.com/c2c")
        assert url == "https://cdn.example.com/c2c/download?encrypted_query_param=abc123"

    def test_download_url_encodes_special_chars(self):
        url = build_cdn_download_url("a b+c", "https://cdn.example.com/c2c")
        assert "a%20b%2Bc" in url

    def test_upload_url(self):
        url = build_cdn_upload_url("https://cdn.example.com/c2c", "up_param", "fk_123")
        assert "upload?" in url
        assert "encrypted_query_param=up_param" in url
        assert "filekey=fk_123" in url
