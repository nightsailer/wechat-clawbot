"""Tests for inbound message conversion."""

from wechat_clawbot.api.types import (
    MessageItem,
    MessageItemType,
    RefMessage,
    TextItem,
    VoiceItem,
    WeixinMessage,
)
from wechat_clawbot.messaging.inbound import (
    get_context_token,
    is_media_item,
    set_context_token,
    weixin_message_to_msg_context,
)


class TestContextTokenStore:
    def test_set_and_get(self):
        set_context_token("acc1", "user1", "token-abc")
        assert get_context_token("acc1", "user1") == "token-abc"

    def test_get_missing(self):
        assert get_context_token("acc1", "nonexistent") is None


class TestIsMediaItem:
    def test_text_is_not_media(self):
        assert not is_media_item(MessageItem(type=MessageItemType.TEXT))

    def test_image_is_media(self):
        assert is_media_item(MessageItem(type=MessageItemType.IMAGE))

    def test_video_is_media(self):
        assert is_media_item(MessageItem(type=MessageItemType.VIDEO))


class TestWeixinMessageToMsgContext:
    def test_basic_text(self):
        msg = WeixinMessage(
            from_user_id="user@im.wechat",
            item_list=[MessageItem(type=MessageItemType.TEXT, text_item=TextItem(text="hello"))],
            context_token="ctx-123",
        )
        ctx = weixin_message_to_msg_context(msg, "bot-account")
        assert ctx.body == "hello"
        assert ctx.from_user == "user@im.wechat"
        assert ctx.to == "user@im.wechat"
        assert ctx.account_id == "bot-account"
        assert ctx.context_token == "ctx-123"
        assert ctx.provider == "openclaw-weixin"

    def test_voice_with_text_uses_transcription(self):
        msg = WeixinMessage(
            from_user_id="u1",
            item_list=[
                MessageItem(
                    type=MessageItemType.VOICE,
                    voice_item=VoiceItem(text="transcribed text"),
                )
            ],
        )
        ctx = weixin_message_to_msg_context(msg, "acc")
        assert ctx.body == "transcribed text"

    def test_quoted_text(self):
        msg = WeixinMessage(
            from_user_id="u1",
            item_list=[
                MessageItem(
                    type=MessageItemType.TEXT,
                    text_item=TextItem(text="reply"),
                    ref_msg=RefMessage(title="original"),
                )
            ],
        )
        ctx = weixin_message_to_msg_context(msg, "acc")
        assert "[引用: original]" in ctx.body
        assert "reply" in ctx.body

    def test_empty_message(self):
        msg = WeixinMessage(from_user_id="u1")
        ctx = weixin_message_to_msg_context(msg, "acc")
        assert ctx.body == ""
