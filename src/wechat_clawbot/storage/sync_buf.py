"""Persistent get_updates_buf storage for the long-poll monitor."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from wechat_clawbot.auth.accounts import derive_raw_account_id, resolve_accounts_dir
from wechat_clawbot.storage.state_dir import resolve_state_dir

if TYPE_CHECKING:
    from pathlib import Path


def get_sync_buf_file_path(account_id: str) -> Path:
    """Path to the persistent ``get_updates_buf`` file for an account."""
    return resolve_accounts_dir() / f"{account_id}.sync.json"


def _legacy_sync_buf_default_json_path() -> Path:
    return (
        resolve_state_dir()
        / "agents"
        / "default"
        / "sessions"
        / ".openclaw-weixin-sync"
        / "default.json"
    )


def _read_sync_buf_file(file_path: Path) -> str | None:
    try:
        data = json.loads(file_path.read_text("utf-8"))
        buf = data.get("get_updates_buf")
        if isinstance(buf, str):
            return buf
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return None


def load_get_updates_buf(file_path: Path) -> str | None:
    """Load persisted ``get_updates_buf`` with compatibility fallbacks.

    1. Primary path (normalized accountId)
    2. Compat path (raw accountId derived from pattern)
    3. Legacy single-account path
    """
    value = _read_sync_buf_file(file_path)
    if value is not None:
        return value

    account_id = file_path.stem.removesuffix(".sync")
    raw_id = derive_raw_account_id(account_id)
    if raw_id:
        compat_path = resolve_accounts_dir() / f"{raw_id}.sync.json"
        compat_value = _read_sync_buf_file(compat_path)
        if compat_value is not None:
            return compat_value

    return _read_sync_buf_file(_legacy_sync_buf_default_json_path())


def save_get_updates_buf(file_path: Path, get_updates_buf: str) -> None:
    """Persist ``get_updates_buf``. Creates parent dir if needed."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps({"get_updates_buf": get_updates_buf}), "utf-8")
