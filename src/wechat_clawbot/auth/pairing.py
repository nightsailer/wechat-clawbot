"""Framework authorization storage integration (allowFrom lists)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from wechat_clawbot.storage.state_dir import resolve_state_dir
from wechat_clawbot.util.logger import logger


def _resolve_credentials_dir() -> Path:
    import os

    override = os.environ.get("OPENCLAW_OAUTH_DIR", "").strip()
    if override:
        return Path(override)
    return resolve_state_dir() / "credentials"


def _safe_key(raw: str) -> str:
    trimmed = raw.strip().lower()
    if not trimmed:
        raise ValueError("invalid key for allowFrom path")
    safe = re.sub(r'[\\/:*?"<>|]', "_", trimmed).replace("..", "_")
    if not safe or safe == "_":
        raise ValueError("invalid key for allowFrom path")
    return safe


def resolve_framework_allow_from_path(account_id: str) -> Path:
    """Path: ``<credDir>/openclaw-weixin-<accountId>-allowFrom.json``."""
    base = _safe_key("openclaw-weixin")
    safe_account = _safe_key(account_id)
    return _resolve_credentials_dir() / f"{base}-{safe_account}-allowFrom.json"


def read_framework_allow_from_list(account_id: str) -> list[str]:
    """Read the framework allowFrom list for an account. Returns empty list if missing."""
    file_path = resolve_framework_allow_from_path(account_id)
    try:
        parsed = json.loads(file_path.read_text("utf-8"))
        allow_from = parsed.get("allowFrom", [])
        if isinstance(allow_from, list):
            return [i for i in allow_from if isinstance(i, str) and i.strip()]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return []


async def register_user_in_framework_store(
    account_id: str,
    user_id: str,
) -> bool:
    """Register a user ID in the framework's channel allowFrom store.

    Returns ``True`` if the list was changed.
    """
    trimmed = user_id.strip()
    if not trimmed:
        return False
    file_path = resolve_framework_allow_from_path(account_id)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing content, or start with empty structure if file is missing
    try:
        content = json.loads(file_path.read_text("utf-8"))
        allow_from = content.get("allowFrom", [])
        if not isinstance(allow_from, list):
            allow_from = []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        content = {"version": 1}
        allow_from = []

    if trimmed in allow_from:
        return False

    allow_from.append(trimmed)
    content["allowFrom"] = allow_from
    file_path.write_text(json.dumps(content, indent=2), "utf-8")
    logger.info(
        f"registerUserInFrameworkStore: added userId={trimmed} "
        f"accountId={account_id} path={file_path}"
    )
    return True
