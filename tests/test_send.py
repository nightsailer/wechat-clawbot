"""Tests for send module (markdown conversion)."""

from wechat_clawbot.messaging.send import markdown_to_plain_text


class TestMarkdownToPlainText:
    def test_code_blocks(self):
        md = "before\n```python\nprint('hi')\n```\nafter"
        result = markdown_to_plain_text(md)
        assert "```" not in result
        assert "print('hi')" in result

    def test_images_removed(self):
        md = "text ![alt](http://img.png) more"
        result = markdown_to_plain_text(md)
        assert "![" not in result
        assert "http://img.png" not in result

    def test_links_keep_text(self):
        md = "click [here](http://example.com)"
        result = markdown_to_plain_text(md)
        assert "here" in result
        assert "http://example.com" not in result

    def test_bold_stripped(self):
        md = "this is **bold** text"
        result = markdown_to_plain_text(md)
        assert result == "this is bold text"

    def test_headers_stripped(self):
        md = "## Title\nContent"
        result = markdown_to_plain_text(md)
        assert "##" not in result
        assert "Title" in result

    def test_plain_text_unchanged(self):
        text = "Just plain text here"
        assert markdown_to_plain_text(text) == text
