"""Tests for context token disk persistence (round-trip, restore, clear)."""

from __future__ import annotations

import json
from unittest import mock

from wechat_clawbot.messaging import inbound as inbound_mod
from wechat_clawbot.messaging.inbound import (
    clear_context_tokens_for_account,
    find_account_ids_by_context_token,
    get_context_token,
    get_restored_tokens_for_server,
    restore_context_tokens,
    set_context_token,
)


def _reset_store() -> None:
    """Clear the module-level _context_token_store between tests."""
    inbound_mod._context_token_store.clear()


def _mock_accounts_dir(tmp_path):
    """Mock resolve_accounts_dir to point at tmp_path (files land directly in tmp_path/)."""
    return mock.patch.object(inbound_mod, "resolve_accounts_dir", return_value=tmp_path)


class TestContextTokenPersistence:
    """Round-trip: set -> persist -> clear memory -> restore -> get."""

    def setup_method(self):
        _reset_store()

    def test_round_trip(self, tmp_path):
        """Tokens survive a simulated restart (persist -> clear -> restore)."""
        with _mock_accounts_dir(tmp_path):
            set_context_token("acc-a", "user1", "tok-1")
            set_context_token("acc-a", "user2", "tok-2")
            assert get_context_token("acc-a", "user1") == "tok-1"

            # Simulate restart: clear memory, then restore from disk
            _reset_store()
            assert get_context_token("acc-a", "user1") is None

            restore_context_tokens("acc-a")
            assert get_context_token("acc-a", "user1") == "tok-1"
            assert get_context_token("acc-a", "user2") == "tok-2"

    def test_persist_writes_json_file(self, tmp_path):
        """set_context_token writes a JSON file to the expected path."""
        with _mock_accounts_dir(tmp_path):
            set_context_token("acc-b", "u1", "t1")
            fp = tmp_path / "acc-b.context-tokens.json"
            assert fp.exists()
            data = json.loads(fp.read_text("utf-8"))
            assert data == {"u1": "t1"}

    def test_restore_nonexistent_file_is_noop(self, tmp_path):
        """restore_context_tokens with no file on disk does nothing."""
        with _mock_accounts_dir(tmp_path):
            restore_context_tokens("no-such-account")
            assert get_context_token("no-such-account", "x") is None

    def test_restore_corrupted_json_does_not_crash(self, tmp_path):
        """Corrupted JSON file -> logged error, no crash, no tokens restored."""
        with _mock_accounts_dir(tmp_path):
            fp = tmp_path / "acc-c.context-tokens.json"
            fp.write_text("{invalid json", "utf-8")
            restore_context_tokens("acc-c")
            assert get_context_token("acc-c", "any") is None

    def test_restore_non_dict_json_does_not_crash(self, tmp_path):
        """JSON file containing a list instead of dict -> logged error, no crash."""
        with _mock_accounts_dir(tmp_path):
            fp = tmp_path / "acc-d.context-tokens.json"
            fp.write_text('["not", "a", "dict"]', "utf-8")
            restore_context_tokens("acc-d")
            assert get_context_token("acc-d", "any") is None

    def test_restore_skips_non_string_values(self, tmp_path):
        """Non-string or empty token values in JSON are skipped."""
        with _mock_accounts_dir(tmp_path):
            fp = tmp_path / "acc-e.context-tokens.json"
            fp.write_text(json.dumps({"u1": "good", "u2": 123, "u3": ""}), "utf-8")
            restore_context_tokens("acc-e")
            assert get_context_token("acc-e", "u1") == "good"
            assert get_context_token("acc-e", "u2") is None
            assert get_context_token("acc-e", "u3") is None

    def test_unchanged_token_skips_disk_write(self, tmp_path):
        """Setting the same token twice should skip the second disk write."""
        with _mock_accounts_dir(tmp_path):
            set_context_token("acc-skip", "u1", "same-tok")

            # Patch _persist to track calls — second set with same value should skip
            with mock.patch.object(inbound_mod, "_persist_context_tokens") as mock_persist:
                set_context_token("acc-skip", "u1", "same-tok")
                mock_persist.assert_not_called()


class TestClearContextTokensForAccount:
    def setup_method(self):
        _reset_store()

    def test_clear_removes_memory_and_disk(self, tmp_path):
        with _mock_accounts_dir(tmp_path):
            set_context_token("acc-f", "u1", "t1")
            set_context_token("acc-f", "u2", "t2")
            fp = tmp_path / "acc-f.context-tokens.json"
            assert fp.exists()

            clear_context_tokens_for_account("acc-f")
            assert get_context_token("acc-f", "u1") is None
            assert get_context_token("acc-f", "u2") is None
            assert not fp.exists()

    def test_clear_does_not_affect_other_accounts(self, tmp_path):
        with _mock_accounts_dir(tmp_path):
            set_context_token("acc-g", "u1", "t1")
            set_context_token("acc-h", "u1", "t2")
            clear_context_tokens_for_account("acc-g")
            assert get_context_token("acc-g", "u1") is None
            assert get_context_token("acc-h", "u1") == "t2"


class TestFindAccountIdsByContextToken:
    def setup_method(self):
        _reset_store()

    def test_finds_matching_accounts(self):
        inbound_mod._context_token_store["a1:user@im"] = "tok1"
        inbound_mod._context_token_store["a2:user@im"] = "tok2"
        inbound_mod._context_token_store["a3:other@im"] = "tok3"
        result = find_account_ids_by_context_token(["a1", "a2", "a3"], "user@im")
        assert sorted(result) == ["a1", "a2"]

    def test_returns_empty_on_no_match(self):
        assert find_account_ids_by_context_token(["a1", "a2"], "nobody") == []

    def test_empty_input_returns_empty(self):
        assert find_account_ids_by_context_token([], "user") == []


class TestGetRestoredTokensForServer:
    def setup_method(self):
        _reset_store()

    def test_returns_tokens_for_account(self):
        inbound_mod._context_token_store["acc:u1"] = "t1"
        inbound_mod._context_token_store["acc:u2"] = "t2"
        inbound_mod._context_token_store["other:u1"] = "t3"
        result = get_restored_tokens_for_server("acc")
        assert result == {"u1": "t1", "u2": "t2"}

    def test_returns_empty_for_unknown_account(self):
        assert get_restored_tokens_for_server("nope") == {}
