"""Tests for PollerManager — multi-account poller management (Task 5.1)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
import pytest

from wechat_clawbot.gateway.poller import PollerManager

if TYPE_CHECKING:
    from wechat_clawbot.gateway.types import InboundMessage


class TestPollerManagerBasic:
    def test_init_empty(self, tmp_path):
        mgr = PollerManager(tmp_path)
        assert mgr.account_ids == []
        assert len(mgr) == 0

    def test_add_account(self, tmp_path):
        mgr = PollerManager(tmp_path)

        async def noop(msg: InboundMessage) -> None:
            pass

        mgr.add_account("acc-1", "https://example.com", "tok", noop)
        assert "acc-1" in mgr.account_ids
        assert len(mgr) == 1

    def test_add_multiple_accounts(self, tmp_path):
        mgr = PollerManager(tmp_path)

        async def noop(msg: InboundMessage) -> None:
            pass

        mgr.add_account("acc-1", "https://example.com", "tok1", noop)
        mgr.add_account("acc-2", "https://example.com", "tok2", noop)
        assert set(mgr.account_ids) == {"acc-1", "acc-2"}
        assert len(mgr) == 2

    def test_remove_account(self, tmp_path):
        mgr = PollerManager(tmp_path)

        async def noop(msg: InboundMessage) -> None:
            pass

        mgr.add_account("acc-1", "https://example.com", "tok", noop)
        removed = mgr.remove_account("acc-1")
        assert removed is not None
        assert "acc-1" not in mgr.account_ids
        assert len(mgr) == 0

    def test_remove_nonexistent(self, tmp_path):
        mgr = PollerManager(tmp_path)
        removed = mgr.remove_account("nonexistent")
        assert removed is None

    def test_get_poller(self, tmp_path):
        mgr = PollerManager(tmp_path)

        async def noop(msg: InboundMessage) -> None:
            pass

        mgr.add_account("acc-1", "https://example.com", "tok", noop)
        poller = mgr.get_poller("acc-1")
        assert poller is not None
        assert poller.account_id == "acc-1"

    def test_get_poller_not_found(self, tmp_path):
        mgr = PollerManager(tmp_path)
        assert mgr.get_poller("nonexistent") is None


class TestPollerManagerStartAll:
    @pytest.mark.anyio()
    async def test_start_all_empty(self, tmp_path):
        """start_all with no accounts should wait for stop event."""
        mgr = PollerManager(tmp_path)
        stop = anyio.Event()

        async with anyio.create_task_group() as tg:
            tg.start_soon(mgr.start_all, stop)
            # Give it a moment, then stop
            await anyio.sleep(0.05)
            stop.set()


class TestSessionAccountResolver:
    """Tests for record_user_account and resolve_account in SessionStore."""

    def test_record_and_resolve(self, tmp_path):
        from wechat_clawbot.gateway.session import SessionStore

        store = SessionStore(tmp_path / "users")
        store.create_user("user-1")

        store.record_user_account("user-1", "acc-A")
        assert store.resolve_account("user-1") == "acc-A"

    def test_record_updates_account(self, tmp_path):
        from wechat_clawbot.gateway.session import SessionStore

        store = SessionStore(tmp_path / "users")
        store.create_user("user-1")

        store.record_user_account("user-1", "acc-A")
        store.record_user_account("user-1", "acc-B")
        assert store.resolve_account("user-1") == "acc-B"

    def test_record_same_account_no_update(self, tmp_path):
        from wechat_clawbot.gateway.session import SessionStore

        store = SessionStore(tmp_path / "users")
        user = store.create_user("user-1")
        user.account_id = "acc-A"
        store.update_user(user)

        store.record_user_account("user-1", "acc-A")
        # account_id unchanged so update_user not called again with new ts
        # (it is called only if account_id differs)
        reloaded = store.get_user("user-1")
        assert reloaded is not None
        assert reloaded.account_id == "acc-A"

    def test_resolve_unknown_user(self, tmp_path):
        from wechat_clawbot.gateway.session import SessionStore

        store = SessionStore(tmp_path / "users")
        assert store.resolve_account("nonexistent") == ""

    def test_record_unknown_user_noop(self, tmp_path):
        from wechat_clawbot.gateway.session import SessionStore

        store = SessionStore(tmp_path / "users")
        # Should not raise
        store.record_user_account("nonexistent", "acc-A")
