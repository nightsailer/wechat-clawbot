"""Tests for iLink-App-ClientVersion encoding."""

from wechat_clawbot.api.client import _build_client_version


class TestBuildClientVersion:
    def test_zero(self):
        assert _build_client_version("0.0.0") == 0

    def test_current_version(self):
        # 0.2.0 -> 0x00_00_02_00 = 512
        assert _build_client_version("0.2.0") == 0x00000200

    def test_major_only(self):
        # 1.0.0 -> 0x00_01_00_00 = 65536
        assert _build_client_version("1.0.0") == 0x00010000

    def test_all_parts(self):
        # 1.2.3 -> 0x00_01_02_03 = 66051
        assert _build_client_version("1.2.3") == 0x00010203

    def test_patch_only(self):
        assert _build_client_version("0.0.1") == 1

    def test_two_segments(self):
        # "1.2" -> patch defaults to 0
        assert _build_client_version("1.2") == 0x00010200

    def test_single_segment(self):
        # "3" -> minor/patch default to 0
        assert _build_client_version("3") == 0x00030000

    def test_large_values_clamped_to_byte(self):
        # 256 -> 0xFF mask -> 0
        assert _build_client_version("256.0.0") == 0

    def test_max_byte_values(self):
        # 255.255.255 -> 0x00_FF_FF_FF
        assert _build_client_version("255.255.255") == 0x00FFFFFF
