"""Long-poll monitor loop: getUpdates -> processOneMessage."""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from wechat_clawbot.api.client import WeixinApiOptions, get_updates
from wechat_clawbot.api.config_cache import WeixinConfigManager
from wechat_clawbot.api.session_guard import (
    SESSION_EXPIRED_ERRCODE,
    get_remaining_pause_ms,
    pause_session,
)
from wechat_clawbot.messaging.process_message import ProcessMessageDeps, process_one_message
from wechat_clawbot.storage.sync_buf import (
    get_sync_buf_file_path,
    load_get_updates_buf,
    save_get_updates_buf,
)
from wechat_clawbot.util.logger import logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_DEFAULT_LONG_POLL_TIMEOUT_MS = 35_000
_MAX_CONSECUTIVE_FAILURES = 3
_BACKOFF_DELAY_MS = 30_000
_RETRY_DELAY_MS = 2_000


@dataclass
class MonitorOpts:
    base_url: str
    cdn_base_url: str
    token: str | None = None
    account_id: str = ""
    config: dict[str, Any] | None = None
    log: Callable[[str], None] = lambda msg: None
    err_log: Callable[[str], None] = lambda msg: None
    long_poll_timeout_ms: int | None = None
    set_status: Callable[[dict], None] | None = None
    save_media: Callable[..., Awaitable[dict[str, str]]] | None = None
    dispatch_reply: Callable[..., Awaitable[None]] | None = None


async def _sleep(ms: int, stop_event: asyncio.Event | None = None) -> None:
    """Sleep with optional cancellation via stop event."""
    if stop_event:
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=ms / 1000.0)
    else:
        await asyncio.sleep(ms / 1000.0)


async def monitor_weixin_provider(
    opts: MonitorOpts,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Long-poll loop: getUpdates -> processOneMessage. Runs until *stop_event* is set."""
    account_id = opts.account_id
    base_url = opts.base_url
    cdn_base_url = opts.cdn_base_url
    token = opts.token
    config = opts.config or {}
    log = opts.log
    err_log = opts.err_log
    a_log = logger.with_account(account_id)

    a_log.info("Monitor starting")
    log(f"weixin monitor started ({base_url}, account={account_id})")

    sync_file = get_sync_buf_file_path(account_id)
    previous_buf = load_get_updates_buf(sync_file)
    get_updates_buf = previous_buf or ""

    if previous_buf:
        log(f"[weixin] resuming from previous sync buf ({len(get_updates_buf)} bytes)")
    else:
        log("[weixin] no previous sync buf, starting fresh")

    config_mgr = WeixinConfigManager(WeixinApiOptions(base_url=base_url, token=token), log)

    next_timeout = opts.long_poll_timeout_ms or _DEFAULT_LONG_POLL_TIMEOUT_MS
    consecutive_failures = 0

    while not (stop_event and stop_event.is_set()):
        try:
            resp = await get_updates(
                base_url=base_url,
                token=token,
                get_updates_buf=get_updates_buf,
                timeout_ms=next_timeout,
            )

            if resp.longpolling_timeout_ms and resp.longpolling_timeout_ms > 0:
                next_timeout = resp.longpolling_timeout_ms

            is_api_error = (resp.ret is not None and resp.ret != 0) or (
                resp.errcode is not None and resp.errcode != 0
            )
            if is_api_error:
                is_expired = (
                    resp.errcode == SESSION_EXPIRED_ERRCODE or resp.ret == SESSION_EXPIRED_ERRCODE
                )
                if is_expired:
                    pause_session(account_id)
                    pause_ms = get_remaining_pause_ms(account_id)
                    err_log(f"weixin getUpdates: session expired, pausing {pause_ms // 60_000} min")
                    consecutive_failures = 0
                    await _sleep(pause_ms, stop_event)
                    continue

                consecutive_failures += 1
                err_log(
                    f"weixin getUpdates failed: ret={resp.ret} errcode={resp.errcode} "
                    f"({consecutive_failures}/{_MAX_CONSECUTIVE_FAILURES})"
                )
                if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                    consecutive_failures = 0
                    await _sleep(_BACKOFF_DELAY_MS, stop_event)
                else:
                    await _sleep(_RETRY_DELAY_MS, stop_event)
                continue

            consecutive_failures = 0
            if opts.set_status:
                opts.set_status({"accountId": account_id, "lastEventAt": time.time() * 1000})

            if resp.get_updates_buf:
                save_get_updates_buf(sync_file, resp.get_updates_buf)
                get_updates_buf = resp.get_updates_buf

            for msg in resp.msgs or []:
                a_log.info(
                    f"inbound message: from={msg.from_user_id} "
                    f"types={','.join(str(i.type) for i in (msg.item_list or []))}"
                )
                if opts.set_status:
                    now = time.time() * 1000
                    opts.set_status(
                        {"accountId": account_id, "lastEventAt": now, "lastInboundAt": now}
                    )

                from_user_id = msg.from_user_id or ""
                cached_config = await config_mgr.get_for_user(from_user_id, msg.context_token)

                await process_one_message(
                    msg,
                    ProcessMessageDeps(
                        account_id=account_id,
                        config=config,
                        base_url=base_url,
                        cdn_base_url=cdn_base_url,
                        token=token,
                        typing_ticket=cached_config.typing_ticket,
                        log=log,
                        err_log=err_log,
                        save_media=opts.save_media,
                        dispatch_reply=opts.dispatch_reply,
                    ),
                )

        except Exception as e:
            if stop_event and stop_event.is_set():
                a_log.info("Monitor stopped (cancelled)")
                return
            consecutive_failures += 1
            err_log(
                f"weixin getUpdates error ({consecutive_failures}/{_MAX_CONSECUTIVE_FAILURES}): {e}"
            )
            if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                consecutive_failures = 0
                await _sleep(_BACKOFF_DELAY_MS, stop_event)
            else:
                await _sleep(_RETRY_DELAY_MS, stop_event)

    a_log.info("Monitor ended")
