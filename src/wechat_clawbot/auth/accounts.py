"""Account storage, credential management, and config resolution."""

from __future__ import annotations

import contextlib
import json
import os
import re
from pathlib import Path

from wechat_clawbot.storage.state_dir import resolve_state_dir

DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"
CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"


# ---------------------------------------------------------------------------
# Account ID compatibility (legacy raw ID -> normalized ID)
# ---------------------------------------------------------------------------


def normalize_account_id(raw: str) -> str:
    """Normalize a raw account ID to a filesystem-safe key.

    Replaces ``@``, ``.`` with ``-``.  e.g. ``hex@im.bot`` -> ``hex-im-bot``.
    """
    return re.sub(r"[@.]", "-", raw.strip())


def derive_raw_account_id(normalized_id: str) -> str | None:
    """Pattern-based reverse of ``normalize_account_id`` for known weixin ID suffixes."""
    if normalized_id.endswith("-im-bot"):
        return f"{normalized_id[:-7]}@im.bot"
    if normalized_id.endswith("-im-wechat"):
        return f"{normalized_id[:-10]}@im.wechat"
    return None


# ---------------------------------------------------------------------------
# State directory helpers
# ---------------------------------------------------------------------------


def _resolve_weixin_state_dir() -> Path:
    return resolve_state_dir() / "openclaw-weixin"


def _resolve_account_index_path() -> Path:
    return _resolve_weixin_state_dir() / "accounts.json"


def resolve_accounts_dir() -> Path:
    return _resolve_weixin_state_dir() / "accounts"


def _resolve_account_path(account_id: str) -> Path:
    return resolve_accounts_dir() / f"{account_id}.json"


# ---------------------------------------------------------------------------
# Account data types
# ---------------------------------------------------------------------------


class WeixinAccountData:
    """Unified per-account data: token + baseUrl in one file."""

    __slots__ = ("token", "saved_at", "base_url", "user_id")

    def __init__(
        self,
        token: str | None = None,
        saved_at: str | None = None,
        base_url: str | None = None,
        user_id: str | None = None,
    ) -> None:
        self.token = token
        self.saved_at = saved_at
        self.base_url = base_url
        self.user_id = user_id


class ResolvedWeixinAccount:
    """Resolved account merging config + stored credentials."""

    __slots__ = ("account_id", "base_url", "cdn_base_url", "token", "enabled", "configured", "name")

    def __init__(
        self,
        account_id: str,
        base_url: str,
        cdn_base_url: str,
        token: str | None = None,
        enabled: bool = True,
        configured: bool = False,
        name: str | None = None,
    ) -> None:
        self.account_id = account_id
        self.base_url = base_url
        self.cdn_base_url = cdn_base_url
        self.token = token
        self.enabled = enabled
        self.configured = configured
        self.name = name


# ---------------------------------------------------------------------------
# Account index (persistent list of registered account IDs)
# ---------------------------------------------------------------------------


def list_indexed_weixin_account_ids() -> list[str]:
    """Return all accountIds registered via QR login."""
    file_path = _resolve_account_index_path()
    try:
        parsed = json.loads(file_path.read_text("utf-8"))
        if not isinstance(parsed, list):
            return []
        return [i for i in parsed if isinstance(i, str) and i.strip()]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def register_weixin_account_id(account_id: str) -> None:
    """Add *account_id* to the persistent index (no-op if already present)."""
    dir_ = _resolve_weixin_state_dir()
    dir_.mkdir(parents=True, exist_ok=True)
    existing = list_indexed_weixin_account_ids()
    if account_id in existing:
        return
    updated = [*existing, account_id]
    _resolve_account_index_path().write_text(json.dumps(updated, indent=2), "utf-8")


# ---------------------------------------------------------------------------
# Account store (per-account credential files)
# ---------------------------------------------------------------------------


def _load_legacy_token() -> str | None:
    legacy_path = resolve_state_dir() / "credentials" / "openclaw-weixin" / "credentials.json"
    try:
        parsed = json.loads(legacy_path.read_text("utf-8"))
        token = parsed.get("token")
        return token if isinstance(token, str) else None
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _read_account_file(file_path: Path) -> WeixinAccountData | None:
    try:
        d = json.loads(file_path.read_text("utf-8"))
        return WeixinAccountData(
            token=d.get("token"),
            saved_at=d.get("savedAt"),
            base_url=d.get("baseUrl"),
            user_id=d.get("userId"),
        )
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def load_weixin_account(account_id: str) -> WeixinAccountData | None:
    """Load account data by ID, with compatibility fallbacks."""
    primary = _read_account_file(_resolve_account_path(account_id))
    if primary:
        return primary
    raw_id = derive_raw_account_id(account_id)
    if raw_id:
        compat = _read_account_file(_resolve_account_path(raw_id))
        if compat:
            return compat
    token = _load_legacy_token()
    if token:
        return WeixinAccountData(token=token)
    return None


def save_weixin_account(
    account_id: str,
    *,
    token: str | None = None,
    base_url: str | None = None,
    user_id: str | None = None,
) -> None:
    """Persist account data after QR login (merges into existing file)."""
    dir_ = resolve_accounts_dir()
    dir_.mkdir(parents=True, exist_ok=True)

    existing = load_weixin_account(account_id)
    final_token = (token.strip() if token else None) or (existing.token if existing else None)
    final_base_url = (base_url.strip() if base_url else None) or (
        existing.base_url if existing else None
    )
    final_user_id: str | None = None
    if user_id is not None:
        final_user_id = user_id.strip() or None
    elif existing and existing.user_id:
        final_user_id = existing.user_id.strip() or None

    data: dict = {}
    if final_token:
        from datetime import datetime, timezone

        data["token"] = final_token
        data["savedAt"] = datetime.now(timezone.utc).isoformat()
    if final_base_url:
        data["baseUrl"] = final_base_url
    if final_user_id:
        data["userId"] = final_user_id

    file_path = _resolve_account_path(account_id)
    file_path.write_text(json.dumps(data, indent=2), "utf-8")
    with contextlib.suppress(Exception):
        file_path.chmod(0o600)


def clear_weixin_account(account_id: str) -> None:
    """Remove account data file."""
    with contextlib.suppress(FileNotFoundError):
        _resolve_account_path(account_id).unlink()


# ---------------------------------------------------------------------------
# Config route tag
# ---------------------------------------------------------------------------


def _resolve_config_path() -> Path:
    env = os.environ.get("OPENCLAW_CONFIG", "").strip()
    if env:
        return Path(env)
    return resolve_state_dir() / "openclaw.json"


def load_config_route_tag(account_id: str | None = None) -> str | None:
    """Read ``routeTag`` from openclaw.json."""
    try:
        config_path = _resolve_config_path()
        cfg = json.loads(config_path.read_text("utf-8"))
        channels = cfg.get("channels", {})
        section = channels.get("openclaw-weixin", {})
        if not section:
            return None
        if account_id:
            accounts = section.get("accounts", {})
            tag = accounts.get(account_id, {}).get("routeTag")
            if isinstance(tag, int):
                return str(tag)
            if isinstance(tag, str) and tag.strip():
                return tag.strip()
        rt = section.get("routeTag")
        if isinstance(rt, int):
            return str(rt)
        if isinstance(rt, str) and rt.strip():
            return rt.strip()
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return None


async def trigger_weixin_channel_reload() -> None:
    """No-op stub — reload is handled externally."""


# ---------------------------------------------------------------------------
# Account resolution (merge config + stored credentials)
# ---------------------------------------------------------------------------


def list_weixin_account_ids() -> list[str]:
    """List accountIds from the index file (written at QR login)."""
    return list_indexed_weixin_account_ids()


def resolve_weixin_account(
    cfg: dict | None = None,
    account_id: str | None = None,
) -> ResolvedWeixinAccount:
    """Resolve a weixin account by ID, merging config and stored credentials."""
    raw = account_id.strip() if account_id else None
    if not raw:
        raise ValueError("weixin: accountId is required (no default account)")
    id_ = normalize_account_id(raw)

    # Extract config section
    section: dict = {}
    if cfg:
        channels = cfg.get("channels", {})
        section = channels.get("openclaw-weixin", {})
    account_cfg: dict = section.get("accounts", {}).get(id_, section)

    account_data = load_weixin_account(id_)
    token = (account_data.token.strip() if account_data and account_data.token else None) or None
    state_base_url = account_data.base_url.strip() if account_data and account_data.base_url else ""

    return ResolvedWeixinAccount(
        account_id=id_,
        base_url=state_base_url or DEFAULT_BASE_URL,
        cdn_base_url=(account_cfg.get("cdnBaseUrl", "").strip() or CDN_BASE_URL),
        token=token,
        enabled=account_cfg.get("enabled", True) is not False,
        configured=bool(token),
        name=account_cfg.get("name", "").strip() or None,
    )
