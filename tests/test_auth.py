"""Tests for AuthZModule — user authorization (Task 2.4)."""

from __future__ import annotations

from wechat_clawbot.gateway.auth import AuthZModule
from wechat_clawbot.gateway.config import AuthorizationConfig
from wechat_clawbot.gateway.types import UserRole


def _make_config(**overrides) -> AuthorizationConfig:
    """Create an AuthorizationConfig with sensible defaults."""
    defaults = {
        "mode": "allowlist",
        "admins": ["admin-1"],
        "default_endpoints": ["ep-1"],
    }
    defaults.update(overrides)
    return AuthorizationConfig(**defaults)


class TestIsAdmin:
    def test_admin_recognized(self):
        authz = AuthZModule(_make_config(admins=["admin-1", "admin-2"]))
        assert authz.is_admin("admin-1") is True
        assert authz.is_admin("admin-2") is True

    def test_non_admin(self):
        authz = AuthZModule(_make_config(admins=["admin-1"]))
        assert authz.is_admin("random-user") is False

    def test_empty_admins(self):
        authz = AuthZModule(_make_config(admins=[]))
        assert authz.is_admin("anyone") is False


class TestGetRole:
    def test_admin_role(self):
        authz = AuthZModule(_make_config(admins=["admin-1"]))
        assert authz.get_role("admin-1") == UserRole.ADMIN

    def test_user_role(self):
        authz = AuthZModule(_make_config(admins=["admin-1"]))
        assert authz.get_role("regular-user") == UserRole.USER


class TestIsAllowed:
    def test_open_mode_allows_everyone(self):
        authz = AuthZModule(_make_config(mode="open"))
        assert authz.is_allowed("anyone") is True
        assert authz.is_allowed("random-user") is True

    def test_allowlist_mode_allows_admins(self):
        authz = AuthZModule(_make_config(mode="allowlist", admins=["admin-1"]))
        assert authz.is_allowed("admin-1") is True

    def test_allowlist_mode_rejects_non_admins(self):
        authz = AuthZModule(_make_config(mode="allowlist", admins=["admin-1"]))
        assert authz.is_allowed("random-user") is False

    def test_invite_code_mode_rejects_by_default(self):
        authz = AuthZModule(_make_config(mode="invite-code"))
        assert authz.is_allowed("anyone") is False


class TestCanAccessEndpoint:
    def test_admin_can_access_any(self):
        authz = AuthZModule(_make_config(admins=["admin-1"]))
        assert authz.can_access_endpoint("admin-1", "ep-any", []) is True

    def test_user_can_access_bound_endpoint(self):
        authz = AuthZModule(_make_config(admins=["admin-1"]))
        assert authz.can_access_endpoint("user-1", "ep-1", ["ep-1", "ep-2"]) is True

    def test_user_cannot_access_unbound_endpoint(self):
        authz = AuthZModule(_make_config(admins=["admin-1"]))
        assert authz.can_access_endpoint("user-1", "ep-3", ["ep-1", "ep-2"]) is False

    def test_user_with_empty_bindings(self):
        authz = AuthZModule(_make_config(admins=[]))
        assert authz.can_access_endpoint("user-1", "ep-1", []) is False


class TestDefaultEndpoints:
    def test_returns_configured_defaults(self):
        authz = AuthZModule(_make_config(default_endpoints=["ep-1", "ep-2"]))
        assert authz.default_endpoints == ["ep-1", "ep-2"]

    def test_empty_defaults(self):
        authz = AuthZModule(_make_config(default_endpoints=[]))
        assert authz.default_endpoints == []
