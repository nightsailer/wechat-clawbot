"""Tests for MessageArchive (Phase 6.3)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from wechat_clawbot.gateway.archive import MessageArchive


@pytest.fixture
async def archive(tmp_path: Path) -> MessageArchive:
    """Create and open a MessageArchive in a temporary directory."""
    db_path = tmp_path / "test_archive.db"
    arch = MessageArchive(db_path)
    await arch.open()
    yield arch  # type: ignore[misc]
    await arch.close()


# ---------------------------------------------------------------------------
# open / close
# ---------------------------------------------------------------------------


class TestOpenClose:
    @pytest.mark.asyncio
    async def test_open_creates_database(self, tmp_path: Path) -> None:
        db_path = tmp_path / "sub" / "archive.db"
        arch = MessageArchive(db_path)
        await arch.open()
        assert db_path.exists()
        await arch.close()

    @pytest.mark.asyncio
    async def test_close_is_idempotent(self, tmp_path: Path) -> None:
        db_path = tmp_path / "archive.db"
        arch = MessageArchive(db_path)
        await arch.open()
        await arch.close()
        await arch.close()  # Should not raise

    @pytest.mark.asyncio
    async def test_record_without_open(self, tmp_path: Path) -> None:
        db_path = tmp_path / "archive.db"
        arch = MessageArchive(db_path)
        # Should silently do nothing (no conn)
        await arch.record_inbound("acc-1", "user-1", "ep-1", "hello")


# ---------------------------------------------------------------------------
# record_inbound / record_outbound
# ---------------------------------------------------------------------------


class TestRecording:
    @pytest.mark.asyncio
    async def test_record_inbound(self, archive: MessageArchive) -> None:
        await archive.record_inbound("acc-1", "user-1", "ep-1", "hello")
        messages = await archive.query(sender_id="user-1")
        assert len(messages) == 1
        assert messages[0]["direction"] == "inbound"
        assert messages[0]["account_id"] == "acc-1"
        assert messages[0]["sender_id"] == "user-1"
        assert messages[0]["endpoint_id"] == "ep-1"
        assert messages[0]["content"] == "hello"
        assert messages[0]["timestamp"] > 0

    @pytest.mark.asyncio
    async def test_record_outbound(self, archive: MessageArchive) -> None:
        await archive.record_outbound("acc-1", "user-1", "ep-1", "reply text")
        messages = await archive.query(sender_id="user-1")
        assert len(messages) == 1
        assert messages[0]["direction"] == "outbound"
        assert messages[0]["content"] == "reply text"

    @pytest.mark.asyncio
    async def test_record_with_metadata(self, archive: MessageArchive) -> None:
        await archive.record_inbound("acc-1", "user-1", "ep-1", "hello", metadata={"key": "value"})
        messages = await archive.query(sender_id="user-1")
        assert len(messages) == 1
        assert messages[0]["metadata"] == '{"key": "value"}'

    @pytest.mark.asyncio
    async def test_record_without_metadata(self, archive: MessageArchive) -> None:
        await archive.record_inbound("acc-1", "user-1", "ep-1", "hello")
        messages = await archive.query(sender_id="user-1")
        assert len(messages) == 1
        assert messages[0]["metadata"] is None

    @pytest.mark.asyncio
    async def test_multiple_records(self, archive: MessageArchive) -> None:
        await archive.record_inbound("acc-1", "user-1", "ep-1", "msg1")
        await archive.record_outbound("acc-1", "user-1", "ep-1", "msg2")
        await archive.record_inbound("acc-1", "user-2", "ep-1", "msg3")
        messages = await archive.query()
        assert len(messages) == 3


# ---------------------------------------------------------------------------
# query
# ---------------------------------------------------------------------------


class TestQuery:
    @pytest.mark.asyncio
    async def test_query_empty(self, archive: MessageArchive) -> None:
        messages = await archive.query()
        assert messages == []

    @pytest.mark.asyncio
    async def test_query_filter_by_sender(self, archive: MessageArchive) -> None:
        await archive.record_inbound("acc-1", "user-1", "ep-1", "hello")
        await archive.record_inbound("acc-1", "user-2", "ep-1", "world")
        messages = await archive.query(sender_id="user-1")
        assert len(messages) == 1
        assert messages[0]["sender_id"] == "user-1"

    @pytest.mark.asyncio
    async def test_query_filter_by_endpoint(self, archive: MessageArchive) -> None:
        await archive.record_inbound("acc-1", "user-1", "ep-1", "hello")
        await archive.record_inbound("acc-1", "user-1", "ep-2", "world")
        messages = await archive.query(endpoint_id="ep-2")
        assert len(messages) == 1
        assert messages[0]["endpoint_id"] == "ep-2"

    @pytest.mark.asyncio
    async def test_query_filter_combined(self, archive: MessageArchive) -> None:
        await archive.record_inbound("acc-1", "user-1", "ep-1", "a")
        await archive.record_inbound("acc-1", "user-1", "ep-2", "b")
        await archive.record_inbound("acc-1", "user-2", "ep-1", "c")
        messages = await archive.query(sender_id="user-1", endpoint_id="ep-1")
        assert len(messages) == 1
        assert messages[0]["content"] == "a"

    @pytest.mark.asyncio
    async def test_query_limit(self, archive: MessageArchive) -> None:
        for i in range(10):
            await archive.record_inbound("acc-1", "user-1", "ep-1", f"msg-{i}")
        messages = await archive.query(limit=3)
        assert len(messages) == 3

    @pytest.mark.asyncio
    async def test_query_offset(self, archive: MessageArchive) -> None:
        for i in range(5):
            await archive.record_inbound("acc-1", "user-1", "ep-1", f"msg-{i}")
        messages = await archive.query(limit=100, offset=3)
        assert len(messages) == 2

    @pytest.mark.asyncio
    async def test_query_returns_newest_first(self, archive: MessageArchive) -> None:
        await archive.record_inbound("acc-1", "user-1", "ep-1", "first")
        await archive.record_inbound("acc-1", "user-1", "ep-1", "second")
        messages = await archive.query()
        assert messages[0]["content"] == "second"
        assert messages[1]["content"] == "first"

    @pytest.mark.asyncio
    async def test_query_without_open(self, tmp_path: Path) -> None:
        arch = MessageArchive(tmp_path / "nodb.db")
        messages = await arch.query()
        assert messages == []


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------


class TestCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_removes_old_messages(self, archive: MessageArchive) -> None:
        # Insert a message, then manipulate timestamp to be old
        await archive.record_inbound("acc-1", "user-1", "ep-1", "old message")
        # Set timestamp to 100 days ago
        assert archive._conn is not None
        archive._conn.execute("UPDATE messages SET timestamp = ?", (time.time() - 100 * 86400,))
        archive._conn.commit()

        await archive.record_inbound("acc-1", "user-1", "ep-1", "new message")

        deleted = await archive.cleanup(retention_days=30)
        assert deleted == 1

        messages = await archive.query()
        assert len(messages) == 1
        assert messages[0]["content"] == "new message"

    @pytest.mark.asyncio
    async def test_cleanup_returns_zero_when_nothing_old(self, archive: MessageArchive) -> None:
        await archive.record_inbound("acc-1", "user-1", "ep-1", "fresh")
        deleted = await archive.cleanup(retention_days=30)
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_cleanup_zero_retention_noop(self, archive: MessageArchive) -> None:
        await archive.record_inbound("acc-1", "user-1", "ep-1", "hello")
        deleted = await archive.cleanup(retention_days=0)
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_cleanup_negative_retention_noop(self, archive: MessageArchive) -> None:
        await archive.record_inbound("acc-1", "user-1", "ep-1", "hello")
        deleted = await archive.cleanup(retention_days=-1)
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_cleanup_without_open(self, tmp_path: Path) -> None:
        arch = MessageArchive(tmp_path / "nodb.db")
        deleted = await arch.cleanup(retention_days=30)
        assert deleted == 0
