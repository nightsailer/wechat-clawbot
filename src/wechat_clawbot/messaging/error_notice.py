"""Fire-and-forget error notice to the user."""

from __future__ import annotations

from typing import TYPE_CHECKING

from wechat_clawbot.api.client import WeixinApiOptions
from wechat_clawbot.messaging.send import send_message_weixin
from wechat_clawbot.util.logger import logger

if TYPE_CHECKING:
    from collections.abc import Callable


async def send_weixin_error_notice(
    to: str,
    context_token: str | None,
    message: str,
    base_url: str,
    token: str | None,
    err_log: Callable[[str], None],
) -> None:
    """Send a plain-text error notice. No-op when *context_token* is absent."""
    if not context_token:
        logger.warning(f"sendWeixinErrorNotice: no contextToken for to={to}, cannot notify user")
        return
    try:
        await send_message_weixin(
            to=to,
            text=message,
            opts=WeixinApiOptions(base_url=base_url, token=token, context_token=context_token),
        )
    except Exception as e:
        err_log(f"[weixin] sendWeixinErrorNotice failed to={to}: {e}")
