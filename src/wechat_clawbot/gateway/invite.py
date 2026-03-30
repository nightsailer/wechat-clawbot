"""Invite code management for endpoint binding.

Provides a simple file-backed invite code system that allows admins to
generate short-lived codes which users can redeem to bind to specific
endpoints (or gain access in ``invite-code`` authorization mode).
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import secrets
import tempfile
import time
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class InviteCode:
    """A single invite code record."""

    code: str
    endpoint_id: str
    created_at: float = field(default_factory=time.time)
    max_uses: int = 1  # 0 = unlimited
    used_count: int = 0
    expires_at: float = 0  # 0 = no expiry


class InviteManager:
    """Manages invite codes with JSON file persistence."""

    def __init__(self, state_dir: Path) -> None:
        self._file = state_dir / "invites.json"
        self._invites: dict[str, InviteCode] = {}
        self._load()

    def create(
        self,
        endpoint_id: str,
        max_uses: int = 1,
        ttl_hours: float = 0,
    ) -> str:
        """Create a new invite code.

        Parameters
        ----------
        endpoint_id:
            The endpoint that redeemers will be bound to.
        max_uses:
            Maximum number of redemptions (0 = unlimited).
        ttl_hours:
            Time-to-live in hours (0 = no expiry).

        Returns
        -------
        str
            The generated invite code string.
        """
        code = secrets.token_urlsafe(6)  # ~8 chars
        expires = time.time() + ttl_hours * 3600 if ttl_hours > 0 else 0
        self._invites[code] = InviteCode(
            code=code,
            endpoint_id=endpoint_id,
            max_uses=max_uses,
            expires_at=expires,
        )
        self._save()
        return code

    def redeem(self, code: str) -> str | None:
        """Redeem an invite code.

        Returns the ``endpoint_id`` on success, or ``None`` if the code
        is invalid, expired, or exhausted.
        """
        invite = self._invites.get(code)
        if not invite:
            return None
        if invite.expires_at > 0 and time.time() > invite.expires_at:
            return None
        if invite.max_uses > 0 and invite.used_count >= invite.max_uses:
            return None
        invite.used_count += 1
        self._save()
        return invite.endpoint_id

    def list_active(self) -> list[InviteCode]:
        """Return all invite codes that are still valid (not expired, not exhausted)."""
        now = time.time()
        return [
            i
            for i in self._invites.values()
            if (i.expires_at == 0 or i.expires_at > now)
            and (i.max_uses == 0 or i.used_count < i.max_uses)
        ]

    def revoke(self, code: str) -> bool:
        """Revoke (delete) an invite code. Returns True if found and removed."""
        if code in self._invites:
            del self._invites[code]
            self._save()
            return True
        return False

    def _load(self) -> None:
        """Load invite codes from disk."""
        if not self._file.exists():
            return
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            for item in data:
                invite = InviteCode(**item)
                self._invites[invite.code] = invite
        except Exception:
            logger.exception("Failed to load invites from %s", self._file)

    def _save(self) -> None:
        """Persist invite codes to disk atomically."""
        self._file.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            [asdict(i) for i in self._invites.values()],
            indent=2,
            ensure_ascii=False,
        )
        fd, tmp = tempfile.mkstemp(dir=self._file.parent, suffix=".tmp")
        try:
            os.write(fd, payload.encode())
            os.close(fd)
            os.replace(tmp, self._file)
        except Exception:
            with contextlib.suppress(OSError):
                os.close(fd)
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
