"""Authorization module — user access control."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .types import UserRole

if TYPE_CHECKING:
    from .config import AuthorizationConfig

logger = logging.getLogger(__name__)


class AuthZModule:
    """Manages user authorization based on gateway configuration."""

    def __init__(self, config: AuthorizationConfig) -> None:
        self._config = config
        self._admin_set: set[str] = set(config.admins)

    def is_admin(self, sender_id: str) -> bool:
        return sender_id in self._admin_set

    def get_role(self, sender_id: str) -> UserRole:
        if self.is_admin(sender_id):
            return UserRole.ADMIN
        return UserRole.USER

    def is_allowed(self, sender_id: str) -> bool:
        """Check if sender is allowed to interact with gateway."""
        if self._config.mode == "open":
            return True
        if self._config.mode == "allowlist":
            return sender_id in self._admin_set
        # invite-code mode: user must have been registered previously
        return False

    def can_access_endpoint(
        self, sender_id: str, endpoint_id: str, user_bindings: list[str]
    ) -> bool:
        """Check if user can access a specific endpoint."""
        if self.is_admin(sender_id):
            return True
        return endpoint_id in user_bindings

    @property
    def default_endpoints(self) -> list[str]:
        return self._config.default_endpoints
