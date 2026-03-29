"""Inbound message conversion: WeixinMessage -> WeixinMsgContext."""

from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from wechat_clawbot.api.types import MessageItem, MessageItemType, WeixinMessage
from wechat_clawbot.auth.accounts import resolve_accounts_dir
from wechat_clawbot.util.logger import logger
from wechat_clawbot.util.random import generate_id

if TYPE_CHECKING:
    from wechat_clawbot.media.download import InboundMediaOpts

# ---------------------------------------------------------------------------
# Context token store (in-process cache + disk persistence)
# ---------------------------------------------------------------------------

_CONTEXT_TOKEN_MAX_ENTRIES = 10_000

# OrderedDict provides O(1) move_to_end for LRU eviction.
_context_token_store: OrderedDict[str, str] = OrderedDict()


def _context_token_key(account_id: str, user_id: str) -> str:
    return f"{account_id}:{user_id}"


# ---------------------------------------------------------------------------
# Disk persistence helpers
# ---------------------------------------------------------------------------


def _context_token_file(account_id: str):
    return resolve_accounts_dir() / f"{account_id}.context-tokens.json"


def _tokens_for_account(account_id: str) -> dict[str, str]:
    """Extract {user_id: token} for a single account from the global store."""
    prefix = f"{account_id}:"
    return {k[len(prefix) :]: v for k, v in _context_token_store.items() if k.startswith(prefix)}


def _persist_context_tokens(account_id: str) -> None:
    """Persist all context tokens for a given account to disk.

    Synchronous file I/O — the payload is a small JSON map, so blocking
    time is negligible in practice.
    """
    tokens = _tokens_for_account(account_id)
    file_path = _context_token_file(account_id)
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json.dumps(tokens, separators=(",", ":")), "utf-8")
    except OSError as e:
        logger.error(f"persistContextTokens: failed to write {file_path}: {e}")


def restore_context_tokens(account_id: str) -> None:
    """Restore persisted context tokens for an account into the in-memory map.

    Called once during gateway start to survive restarts.
    """
    file_path = _context_token_file(account_id)
    try:
        raw = file_path.read_text("utf-8")
    except FileNotFoundError:
        return
    except OSError as e:
        logger.warning(f"restoreContextTokens: cannot read {file_path}: {e}")
        return
    try:
        tokens = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(
            f"restoreContextTokens: corrupted JSON in {file_path}, "
            f"tokens lost for account={account_id}: {e}"
        )
        return
    if not isinstance(tokens, dict):
        logger.error(f"restoreContextTokens: expected dict in {file_path}, got {type(tokens).__name__}")
        return
    count = 0
    for user_id, token in tokens.items():
        if isinstance(token, str) and token:
            _context_token_store[_context_token_key(account_id, user_id)] = token
            count += 1
    logger.info(f"restoreContextTokens: restored {count} tokens for account={account_id}")


def clear_context_tokens_for_account(account_id: str) -> None:
    """Remove all context tokens for a given account (memory + disk)."""
    prefix = f"{account_id}:"
    keys_to_remove = [k for k in _context_token_store if k.startswith(prefix)]
    for k in keys_to_remove:
        del _context_token_store[k]
    disk_ok = True
    try:
        _context_token_file(account_id).unlink()
    except FileNotFoundError:
        pass
    except OSError as e:
        disk_ok = False
        logger.warning(f"clearContextTokensForAccount: failed to remove disk file: {e}")
    logger.info(
        f"clearContextTokensForAccount: cleared {len(keys_to_remove)} tokens "
        f"for account={account_id} (disk={'ok' if disk_ok else 'failed'})"
    )


def set_context_token(account_id: str, user_id: str, token: str) -> None:
    """Store a context token for a given account+user pair (memory + disk)."""
    k = _context_token_key(account_id, user_id)
    # Skip disk I/O if token is unchanged (common for consecutive messages).
    if _context_token_store.get(k) == token:
        _context_token_store.move_to_end(k)
        return
    _context_token_store[k] = token
    _context_token_store.move_to_end(k)
    while len(_context_token_store) > _CONTEXT_TOKEN_MAX_ENTRIES:
        _context_token_store.popitem(last=False)
    _persist_context_tokens(account_id)


def get_context_token(account_id: str, user_id: str) -> str | None:
    """Retrieve the cached context token for a given account+user pair."""
    k = _context_token_key(account_id, user_id)
    val = _context_token_store.get(k)
    logger.debug(
        f"getContextToken: key={k} found={val is not None} storeSize={len(_context_token_store)}"
    )
    return val


def find_account_ids_by_context_token(account_ids: list[str], user_id: str) -> list[str]:
    """Find all accountIds that have an active contextToken for the given userId."""
    return [
        aid for aid in account_ids
        if _context_token_store.get(_context_token_key(aid, user_id))
    ]


def get_restored_tokens_for_server(account_id: str) -> dict[str, str]:
    """Return {user_id: token} for all tokens of a given account.

    Used by the MCP server to populate its own context_tokens LRU after restore.
    """
    return _tokens_for_account(account_id)


# ---------------------------------------------------------------------------
# MsgContext
# ---------------------------------------------------------------------------


@dataclass
class WeixinMsgContext:
    """Inbound context passed to the core pipeline (matches MsgContext shape)."""

    body: str = ""
    from_user: str = ""
    to: str = ""
    account_id: str = ""
    originating_channel: str = "openclaw-weixin"
    originating_to: str = ""
    message_sid: str = ""
    timestamp: int | None = None
    provider: str = "openclaw-weixin"
    chat_type: str = "direct"
    session_key: str | None = None
    context_token: str | None = None
    media_url: str | None = None
    media_path: str | None = None
    media_type: str | None = None
    command_body: str | None = None
    command_authorized: bool | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def is_media_item(item: MessageItem) -> bool:
    """Return ``True`` if the item is a media type (image, video, file, or voice)."""
    return item.type in (
        MessageItemType.IMAGE,
        MessageItemType.VIDEO,
        MessageItemType.FILE,
        MessageItemType.VOICE,
    )


def body_from_item_list(item_list: list[MessageItem] | None) -> str:
    if not item_list:
        return ""
    for item in item_list:
        if item.type == MessageItemType.TEXT and item.text_item and item.text_item.text is not None:
            text = str(item.text_item.text)
            ref = item.ref_msg
            if not ref:
                return text
            if ref.message_item and is_media_item(ref.message_item):
                return text
            parts: list[str] = []
            if ref.title:
                parts.append(ref.title)
            if ref.message_item:
                ref_body = body_from_item_list([ref.message_item])
                if ref_body:
                    parts.append(ref_body)
            if not parts:
                return text
            return f"[引用: {' | '.join(parts)}]\n{text}"
        if item.type == MessageItemType.VOICE and item.voice_item and item.voice_item.text:
            return item.voice_item.text
    return ""


def weixin_message_to_msg_context(
    msg: WeixinMessage,
    account_id: str,
    opts: InboundMediaOpts | None = None,
) -> WeixinMsgContext:
    """Convert a :class:`WeixinMessage` to a :class:`WeixinMsgContext`."""

    from_user_id = msg.from_user_id or ""
    ctx = WeixinMsgContext(
        body=body_from_item_list(msg.item_list),
        from_user=from_user_id,
        to=from_user_id,
        account_id=account_id,
        originating_to=from_user_id,
        message_sid=generate_id("openclaw-weixin"),
        timestamp=msg.create_time_ms,
    )
    if msg.context_token:
        ctx.context_token = msg.context_token

    if opts:
        if opts.decrypted_pic_path:
            ctx.media_path = opts.decrypted_pic_path
            ctx.media_type = "image/*"
        elif opts.decrypted_video_path:
            ctx.media_path = opts.decrypted_video_path
            ctx.media_type = "video/mp4"
        elif opts.decrypted_file_path:
            ctx.media_path = opts.decrypted_file_path
            ctx.media_type = opts.file_media_type or "application/octet-stream"
        elif opts.decrypted_voice_path:
            ctx.media_path = opts.decrypted_voice_path
            ctx.media_type = opts.voice_media_type or "audio/wav"

    return ctx
