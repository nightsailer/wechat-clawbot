"""Session store — manages per-user state with file persistence."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import tempfile
import time
from typing import TYPE_CHECKING, Any

from wechat_clawbot.messaging.inbound import get_context_token, set_context_token

from .types import EndpointBinding, EndpointSession, UserRole, UserState

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


def _normalize_user_id(user_id: str) -> str:
    """Convert sender_id to filesystem-safe filename."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", user_id)


class SessionStore:
    """Manages user sessions with JSON file persistence."""

    def __init__(self, users_dir: Path) -> None:
        self._users_dir = users_dir
        self._users_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, UserState] = {}
        self._load_all()

    def _load_all(self) -> None:
        """Load all user state files on startup."""
        for f in self._users_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                user = self._dict_to_user_state(data)
                self._cache[user.user_id] = user
            except Exception:
                logger.exception("Failed to load user state from %s", f)

    def _user_file(self, user_id: str) -> Path:
        return self._users_dir / f"{_normalize_user_id(user_id)}.json"

    def _save(self, user: UserState) -> None:
        """Persist user state to disk atomically."""
        path = self._user_file(user.user_id)
        data = self._user_state_to_dict(user)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            os.write(fd, json.dumps(data, indent=2, ensure_ascii=False).encode())
            os.close(fd)
            os.replace(tmp, path)
        except Exception:
            with contextlib.suppress(OSError):
                os.close(fd)
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def get_user(self, user_id: str) -> UserState | None:
        return self._cache.get(user_id)

    def create_user(
        self,
        user_id: str,
        display_name: str = "",
        role: UserRole = UserRole.USER,
        default_endpoints: list[str] | None = None,
    ) -> UserState:
        """Create a new user with optional default endpoint bindings."""
        now = time.time()
        bindings = []
        active_endpoint = ""
        if default_endpoints:
            for eid in default_endpoints:
                bindings.append(EndpointBinding(endpoint_id=eid, bound_at=now))
            active_endpoint = default_endpoints[0]

        user = UserState(
            user_id=user_id,
            display_name=display_name,
            role=role,
            active_endpoint=active_endpoint,
            bindings=bindings,
            created_at=now,
            last_active_at=now,
        )
        self._cache[user_id] = user
        self._save(user)
        return user

    def update_user(self, user: UserState) -> None:
        """Update and persist user state."""
        user.last_active_at = time.time()
        self._cache[user.user_id] = user
        self._save(user)

    def set_active_endpoint(self, user_id: str, endpoint_id: str) -> bool:
        """Switch user's active endpoint. Returns False if user not found."""
        user = self._cache.get(user_id)
        if not user:
            return False
        if not user.is_bound_to(endpoint_id):
            return False
        user.active_endpoint = endpoint_id
        self.update_user(user)
        return True

    def get_active_endpoint(self, user_id: str) -> str:
        """Return user's active endpoint ID, or empty string."""
        user = self._cache.get(user_id)
        return user.active_endpoint if user else ""

    def bind_endpoint(self, user_id: str, endpoint_id: str) -> bool:
        """Bind user to an endpoint."""
        user = self._cache.get(user_id)
        if not user:
            return False
        if user.is_bound_to(endpoint_id):
            return True  # already bound
        user.bindings.append(EndpointBinding(endpoint_id=endpoint_id))
        if not user.active_endpoint:
            user.active_endpoint = endpoint_id
        self.update_user(user)
        return True

    def unbind_endpoint(self, user_id: str, endpoint_id: str) -> bool:
        """Unbind user from an endpoint."""
        user = self._cache.get(user_id)
        if not user:
            return False
        user.bindings = [b for b in user.bindings if b.endpoint_id != endpoint_id]
        if user.active_endpoint == endpoint_id:
            user.active_endpoint = user.bindings[0].endpoint_id if user.bindings else ""
        self.update_user(user)
        return True

    def record_user_account(self, user_id: str, account_id: str) -> None:
        """Record which Bot account a user communicates through.

        Updates the user's ``account_id`` if it has changed, so replies
        can be routed back through the correct account.
        """
        user = self._cache.get(user_id)
        if user is None:
            return
        if user.account_id != account_id:
            user.account_id = account_id
            self.update_user(user)

    def resolve_account(self, user_id: str) -> str:
        """Resolve which Bot account to use for sending to this user.

        Returns the ``account_id`` last recorded for this user, or an
        empty string if unknown.
        """
        user = self._cache.get(user_id)
        return user.account_id if user else ""

    def list_users(self) -> list[UserState]:
        return list(self._cache.values())

    def get_context_token(self, account_id: str, user_id: str) -> str | None:
        """Delegate to messaging.inbound context token store."""
        return get_context_token(account_id, user_id)

    def set_context_token(self, account_id: str, user_id: str, token: str) -> None:
        """Delegate to messaging.inbound context token store."""
        set_context_token(account_id, user_id, token)

    @staticmethod
    def _user_state_to_dict(user: UserState) -> dict[str, Any]:
        """Serialize UserState to JSON-compatible dict."""
        return {
            "user_id": user.user_id,
            "display_name": user.display_name,
            "role": user.role.value,
            "active_endpoint": user.active_endpoint,
            "account_id": user.account_id,
            "bindings": [
                {
                    "endpoint_id": b.endpoint_id,
                    "bound_at": b.bound_at,
                    "permissions": b.permissions,
                    "last_message_at": b.last_message_at,
                }
                for b in user.bindings
            ],
            "endpoint_sessions": {
                k: {
                    "context_token": v.context_token,
                    "last_message_at": v.last_message_at,
                    "state": v.state,
                }
                for k, v in user.endpoint_sessions.items()
            },
            "created_at": user.created_at,
            "last_active_at": user.last_active_at,
        }

    @staticmethod
    def _dict_to_user_state(data: dict[str, Any]) -> UserState:
        """Deserialize dict to UserState."""
        bindings = [
            EndpointBinding(
                endpoint_id=b["endpoint_id"],
                bound_at=b.get("bound_at", 0),
                permissions=b.get("permissions", ["read", "write"]),
                last_message_at=b.get("last_message_at", 0),
            )
            for b in data.get("bindings", [])
        ]
        sessions = {
            k: EndpointSession(
                context_token=v.get("context_token"),
                last_message_at=v.get("last_message_at", 0),
                state=v.get("state", {}),
            )
            for k, v in data.get("endpoint_sessions", {}).items()
        }
        return UserState(
            user_id=data["user_id"],
            display_name=data.get("display_name", ""),
            role=UserRole(data.get("role", "user")),
            active_endpoint=data.get("active_endpoint", ""),
            bindings=bindings,
            endpoint_sessions=sessions,
            account_id=data.get("account_id", ""),
            created_at=data.get("created_at", 0),
            last_active_at=data.get("last_active_at", 0),
        )
