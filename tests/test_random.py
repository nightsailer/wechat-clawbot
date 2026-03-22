"""Tests for random ID generation."""

from wechat_clawbot.util.random import generate_id, temp_file_name


class TestRandom:
    def test_generate_id_format(self):
        id_ = generate_id("test")
        assert id_.startswith("test:")
        parts = id_.split(":")
        assert len(parts) == 2
        ts_hex = parts[1]
        assert "-" in ts_hex

    def test_generate_id_unique(self):
        ids = {generate_id("test") for _ in range(100)}
        assert len(ids) == 100

    def test_temp_file_name(self):
        name = temp_file_name("weixin", ".jpg")
        assert name.startswith("weixin-")
        assert name.endswith(".jpg")

    def test_temp_file_name_unique(self):
        names = {temp_file_name("x", ".bin") for _ in range(100)}
        assert len(names) == 100
