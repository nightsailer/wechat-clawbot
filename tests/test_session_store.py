"""Tests for SessionStore — per-user state management with file persistence (Task 2.4)."""

from __future__ import annotations

import json

from wechat_clawbot.gateway.session import SessionStore, _normalize_user_id
from wechat_clawbot.gateway.types import EndpointBinding, EndpointSession, UserRole, UserState


class TestNormalizeUserId:
    def test_simple_id(self):
        assert _normalize_user_id("user123") == "user123"

    def test_with_special_chars(self):
        assert _normalize_user_id("user@name.com") == "user_name_com"

    def test_with_slashes(self):
        assert _normalize_user_id("path/to/user") == "path_to_user"

    def test_preserves_hyphens_and_underscores(self):
        assert _normalize_user_id("user-name_123") == "user-name_123"


class TestCreateAndGetUser:
    def test_create_user_basic(self, tmp_path):
        store = SessionStore(tmp_path / "users")
        user = store.create_user("u1", display_name="Alice")

        assert user.user_id == "u1"
        assert user.display_name == "Alice"
        assert user.role == UserRole.USER
        assert user.active_endpoint == ""
        assert user.bindings == []

    def test_create_user_with_default_endpoints(self, tmp_path):
        store = SessionStore(tmp_path / "users")
        user = store.create_user("u1", default_endpoints=["ep-1", "ep-2"])

        assert user.active_endpoint == "ep-1"
        assert len(user.bindings) == 2
        assert user.bindings[0].endpoint_id == "ep-1"
        assert user.bindings[1].endpoint_id == "ep-2"

    def test_create_user_with_role(self, tmp_path):
        store = SessionStore(tmp_path / "users")
        user = store.create_user("u1", role=UserRole.ADMIN)
        assert user.role == UserRole.ADMIN

    def test_get_user_found(self, tmp_path):
        store = SessionStore(tmp_path / "users")
        store.create_user("u1", display_name="Alice")

        result = store.get_user("u1")
        assert result is not None
        assert result.user_id == "u1"
        assert result.display_name == "Alice"

    def test_get_user_not_found(self, tmp_path):
        store = SessionStore(tmp_path / "users")
        assert store.get_user("nonexistent") is None


class TestUpdateUser:
    def test_update_user_persists(self, tmp_path):
        store = SessionStore(tmp_path / "users")
        user = store.create_user("u1", display_name="Alice")

        user.display_name = "Bob"
        store.update_user(user)

        result = store.get_user("u1")
        assert result is not None
        assert result.display_name == "Bob"

    def test_update_user_sets_last_active_at(self, tmp_path):
        store = SessionStore(tmp_path / "users")
        user = store.create_user("u1")
        old_active = user.last_active_at

        import time

        time.sleep(0.01)
        store.update_user(user)
        assert user.last_active_at > old_active


class TestActiveEndpoint:
    def test_set_active_endpoint(self, tmp_path):
        store = SessionStore(tmp_path / "users")
        store.create_user("u1", default_endpoints=["ep-1", "ep-2"])

        result = store.set_active_endpoint("u1", "ep-2")
        assert result is True
        assert store.get_active_endpoint("u1") == "ep-2"

    def test_set_active_endpoint_not_bound(self, tmp_path):
        store = SessionStore(tmp_path / "users")
        store.create_user("u1", default_endpoints=["ep-1"])

        result = store.set_active_endpoint("u1", "ep-unknown")
        assert result is False
        assert store.get_active_endpoint("u1") == "ep-1"

    def test_set_active_endpoint_user_not_found(self, tmp_path):
        store = SessionStore(tmp_path / "users")
        assert store.set_active_endpoint("nonexistent", "ep-1") is False

    def test_get_active_endpoint_user_not_found(self, tmp_path):
        store = SessionStore(tmp_path / "users")
        assert store.get_active_endpoint("nonexistent") == ""


class TestBindUnbindEndpoint:
    def test_bind_endpoint(self, tmp_path):
        store = SessionStore(tmp_path / "users")
        store.create_user("u1")

        result = store.bind_endpoint("u1", "ep-1")
        assert result is True

        user = store.get_user("u1")
        assert user is not None
        assert user.is_bound_to("ep-1")
        # First bind sets active endpoint
        assert user.active_endpoint == "ep-1"

    def test_bind_endpoint_already_bound(self, tmp_path):
        store = SessionStore(tmp_path / "users")
        store.create_user("u1", default_endpoints=["ep-1"])

        result = store.bind_endpoint("u1", "ep-1")
        assert result is True  # idempotent

    def test_bind_endpoint_user_not_found(self, tmp_path):
        store = SessionStore(tmp_path / "users")
        assert store.bind_endpoint("nonexistent", "ep-1") is False

    def test_unbind_endpoint(self, tmp_path):
        store = SessionStore(tmp_path / "users")
        store.create_user("u1", default_endpoints=["ep-1", "ep-2"])

        result = store.unbind_endpoint("u1", "ep-1")
        assert result is True

        user = store.get_user("u1")
        assert user is not None
        assert not user.is_bound_to("ep-1")
        # Active endpoint should switch to ep-2
        assert user.active_endpoint == "ep-2"

    def test_unbind_last_endpoint(self, tmp_path):
        store = SessionStore(tmp_path / "users")
        store.create_user("u1", default_endpoints=["ep-1"])

        store.unbind_endpoint("u1", "ep-1")
        user = store.get_user("u1")
        assert user is not None
        assert user.active_endpoint == ""

    def test_unbind_endpoint_user_not_found(self, tmp_path):
        store = SessionStore(tmp_path / "users")
        assert store.unbind_endpoint("nonexistent", "ep-1") is False


class TestListUsers:
    def test_list_users(self, tmp_path):
        store = SessionStore(tmp_path / "users")
        store.create_user("u1")
        store.create_user("u2")

        users = store.list_users()
        ids = {u.user_id for u in users}
        assert ids == {"u1", "u2"}

    def test_list_users_empty(self, tmp_path):
        store = SessionStore(tmp_path / "users")
        assert store.list_users() == []


class TestPersistence:
    def test_save_and_reload(self, tmp_path):
        users_dir = tmp_path / "users"
        store1 = SessionStore(users_dir)
        store1.create_user("u1", display_name="Alice", default_endpoints=["ep-1"])

        # Create a second store instance reading from same directory
        store2 = SessionStore(users_dir)
        user = store2.get_user("u1")
        assert user is not None
        assert user.user_id == "u1"
        assert user.display_name == "Alice"
        assert user.active_endpoint == "ep-1"
        assert len(user.bindings) == 1
        assert user.bindings[0].endpoint_id == "ep-1"

    def test_file_created_on_disk(self, tmp_path):
        users_dir = tmp_path / "users"
        store = SessionStore(users_dir)
        store.create_user("u1")

        files = list(users_dir.glob("*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text())
        assert data["user_id"] == "u1"

    def test_load_all_on_startup(self, tmp_path):
        users_dir = tmp_path / "users"
        users_dir.mkdir(parents=True)

        # Write a user file manually
        user_data = {
            "user_id": "manual-user",
            "display_name": "Manual",
            "role": "admin",
            "active_endpoint": "ep-1",
            "bindings": [{"endpoint_id": "ep-1", "bound_at": 1000.0}],
            "endpoint_sessions": {},
            "created_at": 1000.0,
            "last_active_at": 1000.0,
        }
        (users_dir / "manual-user.json").write_text(json.dumps(user_data))

        store = SessionStore(users_dir)
        user = store.get_user("manual-user")
        assert user is not None
        assert user.display_name == "Manual"
        assert user.role == UserRole.ADMIN

    def test_corrupted_file_skipped(self, tmp_path):
        users_dir = tmp_path / "users"
        users_dir.mkdir(parents=True)

        # Write a corrupted file
        (users_dir / "bad.json").write_text("{invalid json")
        # Write a valid file
        user_data = {
            "user_id": "good-user",
            "display_name": "Good",
            "role": "user",
            "active_endpoint": "",
            "bindings": [],
            "endpoint_sessions": {},
            "created_at": 1000.0,
            "last_active_at": 1000.0,
        }
        (users_dir / "good-user.json").write_text(json.dumps(user_data))

        store = SessionStore(users_dir)
        assert store.get_user("good-user") is not None
        assert len(store.list_users()) == 1


class TestSerialization:
    def test_round_trip_user_state(self, tmp_path):
        """Full round-trip: create -> save -> reload -> verify all fields."""
        users_dir = tmp_path / "users"
        store = SessionStore(users_dir)
        user = store.create_user("u1", display_name="Test", role=UserRole.ADMIN)
        user.account_id = "acc-1"
        user.endpoint_sessions["ep-1"] = EndpointSession(
            context_token="tok-123",
            last_message_at=999.0,
            state={"key": "value"},
        )
        store.update_user(user)

        # Reload
        store2 = SessionStore(users_dir)
        loaded = store2.get_user("u1")
        assert loaded is not None
        assert loaded.display_name == "Test"
        assert loaded.role == UserRole.ADMIN
        assert loaded.account_id == "acc-1"
        assert "ep-1" in loaded.endpoint_sessions
        assert loaded.endpoint_sessions["ep-1"].context_token == "tok-123"
        assert loaded.endpoint_sessions["ep-1"].last_message_at == 999.0
        assert loaded.endpoint_sessions["ep-1"].state == {"key": "value"}

    def test_dict_to_user_state_defaults(self):
        """Deserialize with minimal data, check defaults are applied."""
        data = {"user_id": "u1"}
        user = SessionStore._dict_to_user_state(data)
        assert user.user_id == "u1"
        assert user.display_name == ""
        assert user.role == UserRole.USER
        assert user.active_endpoint == ""
        assert user.bindings == []
        assert user.endpoint_sessions == {}
        assert user.account_id == ""
        assert user.created_at == 0
        assert user.last_active_at == 0
