"""Tests for MIME type utilities."""

from wechat_clawbot.media.mime import (
    get_extension_from_content_type_or_url,
    get_extension_from_mime,
    get_mime_from_filename,
)


class TestMime:
    def test_known_extensions(self):
        assert get_mime_from_filename("photo.jpg") == "image/jpeg"
        assert get_mime_from_filename("video.mp4") == "video/mp4"
        assert get_mime_from_filename("doc.pdf") == "application/pdf"

    def test_unknown_extension(self):
        assert get_mime_from_filename("file.xyz") == "application/octet-stream"

    def test_case_insensitive(self):
        assert get_mime_from_filename("PHOTO.JPG") == "image/jpeg"

    def test_extension_from_mime(self):
        assert get_extension_from_mime("image/jpeg") == ".jpg"
        assert get_extension_from_mime("video/mp4") == ".mp4"
        assert get_extension_from_mime("unknown/type") == ".bin"

    def test_extension_from_content_type_or_url(self):
        assert get_extension_from_content_type_or_url("image/png", "http://x/a") == ".png"
        assert get_extension_from_content_type_or_url(None, "http://x/a.jpg") == ".jpg"
        assert get_extension_from_content_type_or_url(None, "http://x/a") == ".bin"
        # Content-Type with charset
        assert get_extension_from_content_type_or_url("image/jpeg; charset=utf-8", "") == ".jpg"
