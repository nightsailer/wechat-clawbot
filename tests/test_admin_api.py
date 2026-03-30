"""Tests for AdminAPI — admin HTTP API (Task 5.4)."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from wechat_clawbot.gateway.admin import AdminAPI
from wechat_clawbot.gateway.config import (
    AccountConfigModel,
    AuthorizationConfig,
    EndpointConfigModel,
    GatewayConfig,
    GatewayServerConfig,
    RoutingConfig,
)
from wechat_clawbot.gateway.endpoint_manager import EndpointManager
from wechat_clawbot.gateway.invite import InviteManager
from wechat_clawbot.gateway.session import SessionStore
from wechat_clawbot.gateway.types import ChannelType, EndpointConfig


def _make_config(**gw_overrides) -> GatewayConfig:
    """Build a minimal GatewayConfig for testing."""
    gw = GatewayServerConfig(**gw_overrides)
    return GatewayConfig(
        gateway=gw,
        accounts={"test-bot": AccountConfigModel(token="tok")},
        endpoints={"ep-1": EndpointConfigModel(name="Endpoint One", type=ChannelType.MCP)},
        routing=RoutingConfig(),
        authorization=AuthorizationConfig(mode="open"),
    )


@pytest.fixture()
def admin_client(tmp_path):
    """Create a TestClient for the AdminAPI."""
    config = _make_config()
    session_store = SessionStore(tmp_path / "users")
    ep_mgr = EndpointManager()
    ep_mgr.register(EndpointConfig(id="ep-1", name="Endpoint One", type=ChannelType.MCP))
    invite_mgr = InviteManager(tmp_path)

    api = AdminAPI(
        config=config,
        session_store=session_store,
        endpoint_manager=ep_mgr,
        invite_manager=invite_mgr,
    )
    return TestClient(api.get_asgi_app())


@pytest.fixture()
def admin_client_with_auth(tmp_path):
    """Create a TestClient with bearer auth enabled."""
    config = _make_config(admin_token="secret-token")
    session_store = SessionStore(tmp_path / "users")
    ep_mgr = EndpointManager()
    ep_mgr.register(EndpointConfig(id="ep-1", name="Endpoint One", type=ChannelType.MCP))
    invite_mgr = InviteManager(tmp_path)

    api = AdminAPI(
        config=config,
        session_store=session_store,
        endpoint_manager=ep_mgr,
        invite_manager=invite_mgr,
    )
    return TestClient(api.get_asgi_app())


@pytest.fixture()
def components(tmp_path):
    """Return (session_store, endpoint_manager, invite_manager) for direct manipulation."""
    session_store = SessionStore(tmp_path / "users")
    ep_mgr = EndpointManager()
    ep_mgr.register(EndpointConfig(id="ep-1", name="Endpoint One", type=ChannelType.MCP))
    invite_mgr = InviteManager(tmp_path)

    config = _make_config()
    api = AdminAPI(
        config=config,
        session_store=session_store,
        endpoint_manager=ep_mgr,
        invite_manager=invite_mgr,
    )
    client = TestClient(api.get_asgi_app())
    return client, session_store, ep_mgr, invite_mgr


class TestBearerAuth:
    def test_rejects_without_token(self, admin_client_with_auth):
        resp = admin_client_with_auth.get("/api/status")
        assert resp.status_code == 401

    def test_rejects_wrong_token(self, admin_client_with_auth):
        resp = admin_client_with_auth.get("/api/status", headers={"Authorization": "Bearer wrong"})
        assert resp.status_code == 401

    def test_accepts_correct_token(self, admin_client_with_auth):
        resp = admin_client_with_auth.get(
            "/api/status", headers={"Authorization": "Bearer secret-token"}
        )
        assert resp.status_code == 200

    def test_no_auth_when_token_empty(self, admin_client):
        resp = admin_client.get("/api/status")
        assert resp.status_code == 200


class TestGetStatus:
    def test_returns_status(self, admin_client):
        resp = admin_client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert "endpoints" in data
        assert "users" in data


class TestListAccounts:
    def test_list_accounts(self, admin_client):
        resp = admin_client.get("/api/accounts")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["accounts"]) == 1
        assert data["accounts"][0]["id"] == "test-bot"


class TestEndpoints:
    def test_list_endpoints(self, admin_client):
        resp = admin_client.get("/api/endpoints")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["endpoints"]) == 1
        assert data["endpoints"][0]["id"] == "ep-1"

    def test_add_endpoint(self, admin_client):
        resp = admin_client.post(
            "/api/endpoints",
            json={"id": "ep-2", "name": "New Endpoint", "type": "mcp"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "ep-2"

        # Verify it appears in the list
        resp2 = admin_client.get("/api/endpoints")
        ids = [e["id"] for e in resp2.json()["endpoints"]]
        assert "ep-2" in ids

    def test_add_duplicate_endpoint(self, admin_client):
        resp = admin_client.post(
            "/api/endpoints",
            json={"id": "ep-1", "name": "Duplicate"},
        )
        assert resp.status_code == 409

    def test_add_endpoint_missing_id(self, admin_client):
        resp = admin_client.post(
            "/api/endpoints",
            json={"name": "No ID"},
        )
        assert resp.status_code == 400

    def test_add_endpoint_invalid_type(self, admin_client):
        resp = admin_client.post(
            "/api/endpoints",
            json={"id": "ep-x", "type": "invalid-type"},
        )
        assert resp.status_code == 400

    def test_remove_endpoint(self, admin_client):
        resp = admin_client.delete("/api/endpoints/ep-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "removed"

    def test_remove_nonexistent_endpoint(self, admin_client):
        resp = admin_client.delete("/api/endpoints/nonexistent")
        assert resp.status_code == 404


class TestUsers:
    def test_list_users_empty(self, admin_client):
        resp = admin_client.get("/api/users")
        assert resp.status_code == 200
        assert resp.json()["users"] == []

    def test_list_users(self, components):
        client, session_store, _, _ = components
        session_store.create_user("user-1", display_name="Alice")

        resp = client.get("/api/users")
        assert resp.status_code == 200
        users = resp.json()["users"]
        assert len(users) == 1
        assert users[0]["user_id"] == "user-1"

    def test_bind_user(self, components):
        client, session_store, _, _ = components
        session_store.create_user("user-1")

        resp = client.post(
            "/api/users/user-1/bind",
            json={"endpoint_id": "ep-1"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "bound"

        # Verify binding
        user = session_store.get_user("user-1")
        assert user is not None
        assert user.is_bound_to("ep-1")

    def test_bind_user_not_found(self, admin_client):
        resp = admin_client.post(
            "/api/users/nonexistent/bind",
            json={"endpoint_id": "ep-1"},
        )
        assert resp.status_code == 404

    def test_bind_user_endpoint_not_found(self, components):
        client, session_store, _, _ = components
        session_store.create_user("user-1")

        resp = client.post(
            "/api/users/user-1/bind",
            json={"endpoint_id": "nonexistent"},
        )
        assert resp.status_code == 404

    def test_unbind_user(self, components):
        client, session_store, _, _ = components
        session_store.create_user("user-1", default_endpoints=["ep-1"])

        resp = client.post(
            "/api/users/user-1/unbind",
            json={"endpoint_id": "ep-1"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "unbound"

    def test_unbind_user_not_found(self, admin_client):
        resp = admin_client.post(
            "/api/users/nonexistent/unbind",
            json={"endpoint_id": "ep-1"},
        )
        assert resp.status_code == 404


class TestInvites:
    def test_list_invites_empty(self, admin_client):
        resp = admin_client.get("/api/invites")
        assert resp.status_code == 200
        assert resp.json()["invites"] == []

    def test_create_invite(self, admin_client):
        resp = admin_client.post(
            "/api/invites",
            json={"endpoint_id": "ep-1"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "code" in data
        assert data["endpoint_id"] == "ep-1"

    def test_create_invite_endpoint_not_found(self, admin_client):
        resp = admin_client.post(
            "/api/invites",
            json={"endpoint_id": "nonexistent"},
        )
        assert resp.status_code == 404

    def test_create_invite_missing_endpoint_id(self, admin_client):
        resp = admin_client.post(
            "/api/invites",
            json={},
        )
        assert resp.status_code == 400

    def test_created_invite_appears_in_list(self, admin_client):
        admin_client.post(
            "/api/invites",
            json={"endpoint_id": "ep-1", "max_uses": 5},
        )
        resp = admin_client.get("/api/invites")
        invites = resp.json()["invites"]
        assert len(invites) == 1
        assert invites[0]["max_uses"] == 5
