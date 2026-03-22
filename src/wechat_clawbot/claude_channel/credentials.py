"""Simple credential store for the Claude Code WeChat channel bridge.

Credentials are saved to ``~/.claude/channels/wechat/account.json``.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


def credentials_dir() -> Path:
    """Return the directory used for channel credentials and state files."""
    return Path.home() / ".claude" / "channels" / "wechat"


def credentials_file_path() -> Path:
    """Return the path to the credentials file."""
    return credentials_dir() / "account.json"


@dataclass
class AccountData:
    token: str
    base_url: str
    account_id: str
    user_id: str | None = None
    saved_at: str | None = None


def load_credentials() -> AccountData | None:
    """Load saved account credentials. Returns ``None`` if not found."""
    try:
        data = json.loads(credentials_file_path().read_text("utf-8"))
        return AccountData(
            token=data["token"],
            base_url=data.get("baseUrl", data.get("base_url", "")),
            account_id=data.get("accountId", data.get("account_id", "")),
            user_id=data.get("userId", data.get("user_id")),
            saved_at=data.get("savedAt", data.get("saved_at")),
        )
    except (FileNotFoundError, json.JSONDecodeError, KeyError, OSError):
        return None


def save_credentials(data: AccountData) -> None:
    """Persist account credentials to disk atomically.

    Writes to a temporary file first, then renames into place to avoid
    leaving a truncated file if the process crashes mid-write.
    """
    dir_ = credentials_dir()
    dir_.mkdir(parents=True, exist_ok=True)
    file_ = credentials_file_path()
    # Use camelCase keys for compatibility with the TS version
    payload = {
        "token": data.token,
        "baseUrl": data.base_url,
        "accountId": data.account_id,
        "userId": data.user_id,
        "savedAt": data.saved_at,
    }
    content = json.dumps(payload, indent=2)

    # Atomic write: temp file -> os.replace
    fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        fd = -1  # mark as closed
        os.replace(tmp_path, file_)
    except BaseException:
        if fd >= 0:
            os.close(fd)
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise

    with contextlib.suppress(OSError):
        file_.chmod(0o600)
