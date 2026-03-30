"""Tests for InviteManager — invite code management (Task 5.3)."""

from __future__ import annotations

import json
import time

from wechat_clawbot.gateway.invite import InviteManager


class TestCreate:
    def test_create_returns_code(self, tmp_path):
        mgr = InviteManager(tmp_path)
        code = mgr.create("ep-1")
        assert isinstance(code, str)
        assert len(code) > 0

    def test_create_unique_codes(self, tmp_path):
        mgr = InviteManager(tmp_path)
        codes = {mgr.create("ep-1") for _ in range(20)}
        assert len(codes) == 20

    def test_create_with_max_uses(self, tmp_path):
        mgr = InviteManager(tmp_path)
        code = mgr.create("ep-1", max_uses=5)
        active = mgr.list_active()
        invite = next(i for i in active if i.code == code)
        assert invite.max_uses == 5

    def test_create_with_ttl(self, tmp_path):
        mgr = InviteManager(tmp_path)
        code = mgr.create("ep-1", ttl_hours=24)
        active = mgr.list_active()
        invite = next(i for i in active if i.code == code)
        assert invite.expires_at > 0
        assert invite.expires_at > time.time()

    def test_create_unlimited(self, tmp_path):
        mgr = InviteManager(tmp_path)
        code = mgr.create("ep-1", max_uses=0)
        active = mgr.list_active()
        invite = next(i for i in active if i.code == code)
        assert invite.max_uses == 0


class TestRedeem:
    def test_redeem_valid(self, tmp_path):
        mgr = InviteManager(tmp_path)
        code = mgr.create("ep-1")
        result = mgr.redeem(code)
        assert result == "ep-1"

    def test_redeem_invalid_code(self, tmp_path):
        mgr = InviteManager(tmp_path)
        assert mgr.redeem("nonexistent") is None

    def test_redeem_exhausted(self, tmp_path):
        mgr = InviteManager(tmp_path)
        code = mgr.create("ep-1", max_uses=1)
        mgr.redeem(code)  # use once
        assert mgr.redeem(code) is None  # second use fails

    def test_redeem_unlimited(self, tmp_path):
        mgr = InviteManager(tmp_path)
        code = mgr.create("ep-1", max_uses=0)
        for _ in range(10):
            assert mgr.redeem(code) == "ep-1"

    def test_redeem_expired(self, tmp_path):
        mgr = InviteManager(tmp_path)
        code = mgr.create("ep-1", ttl_hours=1)
        # Manually expire it
        invite = mgr._invites[code]
        invite.expires_at = time.time() - 1
        assert mgr.redeem(code) is None

    def test_redeem_increments_used_count(self, tmp_path):
        mgr = InviteManager(tmp_path)
        code = mgr.create("ep-1", max_uses=5)
        mgr.redeem(code)
        mgr.redeem(code)
        invite = mgr._invites[code]
        assert invite.used_count == 2


class TestListActive:
    def test_list_active_excludes_exhausted(self, tmp_path):
        mgr = InviteManager(tmp_path)
        code1 = mgr.create("ep-1", max_uses=1)
        code2 = mgr.create("ep-2", max_uses=1)
        mgr.redeem(code1)

        active = mgr.list_active()
        codes = [i.code for i in active]
        assert code1 not in codes
        assert code2 in codes

    def test_list_active_excludes_expired(self, tmp_path):
        mgr = InviteManager(tmp_path)
        code1 = mgr.create("ep-1", ttl_hours=1)
        code2 = mgr.create("ep-2", ttl_hours=1)
        mgr._invites[code1].expires_at = time.time() - 1

        active = mgr.list_active()
        codes = [i.code for i in active]
        assert code1 not in codes
        assert code2 in codes

    def test_list_active_empty(self, tmp_path):
        mgr = InviteManager(tmp_path)
        assert mgr.list_active() == []


class TestRevoke:
    def test_revoke_existing(self, tmp_path):
        mgr = InviteManager(tmp_path)
        code = mgr.create("ep-1")
        assert mgr.revoke(code) is True
        assert mgr.redeem(code) is None

    def test_revoke_nonexistent(self, tmp_path):
        mgr = InviteManager(tmp_path)
        assert mgr.revoke("nonexistent") is False


class TestPersistence:
    def test_save_and_reload(self, tmp_path):
        mgr1 = InviteManager(tmp_path)
        code = mgr1.create("ep-1", max_uses=5)
        mgr1.redeem(code)

        # Reload from same dir
        mgr2 = InviteManager(tmp_path)
        active = mgr2.list_active()
        assert len(active) == 1
        assert active[0].code == code
        assert active[0].used_count == 1
        assert active[0].endpoint_id == "ep-1"

    def test_file_created_on_disk(self, tmp_path):
        mgr = InviteManager(tmp_path)
        mgr.create("ep-1")
        assert (tmp_path / "invites.json").exists()
        data = json.loads((tmp_path / "invites.json").read_text())
        assert len(data) == 1

    def test_load_empty_dir(self, tmp_path):
        mgr = InviteManager(tmp_path)
        assert mgr.list_active() == []

    def test_load_corrupted_file(self, tmp_path):
        (tmp_path / "invites.json").write_text("{bad json")
        mgr = InviteManager(tmp_path)
        assert mgr.list_active() == []
