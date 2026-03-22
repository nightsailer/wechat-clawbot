"""Tests for account management."""

from wechat_clawbot.auth.accounts import derive_raw_account_id, normalize_account_id


class TestNormalizeAccountId:
    def test_normalize(self):
        assert normalize_account_id("hex@im.bot") == "hex-im-bot"
        assert normalize_account_id("abc@im.wechat") == "abc-im-wechat"

    def test_already_normalized(self):
        assert normalize_account_id("hex-im-bot") == "hex-im-bot"


class TestDeriveRawAccountId:
    def test_im_bot(self):
        assert derive_raw_account_id("hex-im-bot") == "hex@im.bot"

    def test_im_wechat(self):
        assert derive_raw_account_id("abc-im-wechat") == "abc@im.wechat"

    def test_unknown_suffix(self):
        assert derive_raw_account_id("some-other-id") is None
