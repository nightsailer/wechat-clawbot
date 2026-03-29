"""Tests for the SQLite delivery queue (Task 1.8).

Uses ``tmp_path`` for the SQLite database file — ``:memory:`` is not
suitable because ``anyio.to_thread.run_sync`` may use a different
thread per call and SQLite in-memory databases are per-connection.
"""

import sqlite3
import time

import pytest

from wechat_clawbot.gateway.delivery import DeliveryQueue
from wechat_clawbot.gateway.types import DeliveryRecord, DeliveryStatus


def _make_record(**overrides) -> DeliveryRecord:
    """Create a DeliveryRecord with sensible defaults."""
    defaults = {
        "message_id": "msg-001",
        "account_id": "acc-1",
        "sender_id": "sender-1",
        "endpoint_id": "ep-1",
        "content": "hello world",
        "created_at": time.time(),
    }
    defaults.update(overrides)
    return DeliveryRecord(**defaults)


class TestLifecycle:
    async def test_open_close(self, tmp_path):
        q = DeliveryQueue(tmp_path / "test.db")
        await q.open()
        assert q._conn is not None
        await q.close()
        assert q._conn is None

    async def test_close_idempotent(self, tmp_path):
        q = DeliveryQueue(tmp_path / "test.db")
        await q.open()
        await q.close()
        await q.close()  # should not raise

    async def test_db_property_before_open_raises(self, tmp_path):
        q = DeliveryQueue(tmp_path / "test.db")
        with pytest.raises(RuntimeError, match="not open"):
            _ = q._db


class TestEnqueueAndQuery:
    async def test_enqueue_returns_row_id(self, tmp_path):
        q = DeliveryQueue(tmp_path / "test.db")
        await q.open()
        try:
            row_id = await q.enqueue(_make_record())
            assert row_id >= 1
        finally:
            await q.close()

    async def test_get_pending_for_endpoint(self, tmp_path):
        q = DeliveryQueue(tmp_path / "test.db")
        await q.open()
        try:
            await q.enqueue(_make_record(message_id="m1", endpoint_id="ep-1"))
            await q.enqueue(_make_record(message_id="m2", endpoint_id="ep-1"))
            await q.enqueue(_make_record(message_id="m3", endpoint_id="ep-2"))

            pending = await q.get_pending_for_endpoint("ep-1")
            assert len(pending) == 2
            assert all(r.endpoint_id == "ep-1" for r in pending)
            assert all(r.status == DeliveryStatus.PENDING for r in pending)
        finally:
            await q.close()

    async def test_get_pending_unknown_endpoint_returns_empty(self, tmp_path):
        q = DeliveryQueue(tmp_path / "test.db")
        await q.open()
        try:
            result = await q.get_pending_for_endpoint("nonexistent")
            assert result == []
        finally:
            await q.close()

    async def test_enqueue_duplicate_message_id_raises(self, tmp_path):
        q = DeliveryQueue(tmp_path / "test.db")
        await q.open()
        try:
            await q.enqueue(_make_record(message_id="dup-1"))
            with pytest.raises(sqlite3.IntegrityError):
                await q.enqueue(_make_record(message_id="dup-1"))
        finally:
            await q.close()


class TestMarkDelivered:
    async def test_mark_delivered_changes_status(self, tmp_path):
        q = DeliveryQueue(tmp_path / "test.db")
        await q.open()
        try:
            await q.enqueue(_make_record(message_id="m1"))
            await q.mark_delivered("m1")

            # Should no longer appear in pending
            pending = await q.get_pending_for_endpoint("ep-1")
            assert len(pending) == 0
        finally:
            await q.close()


class TestMarkExpired:
    async def test_mark_expired_changes_status(self, tmp_path):
        q = DeliveryQueue(tmp_path / "test.db")
        await q.open()
        try:
            await q.enqueue(_make_record(message_id="m1"))
            await q.mark_expired("m1")

            # Should no longer appear in pending
            pending = await q.get_pending_for_endpoint("ep-1")
            assert len(pending) == 0
        finally:
            await q.close()


class TestRetry:
    async def test_retry_pending_increments_retry_count(self, tmp_path):
        q = DeliveryQueue(tmp_path / "test.db")
        await q.open()
        try:
            await q.enqueue(_make_record(message_id="m1"))
            await q.retry_pending("m1", retry_delay=0.0)

            # After retry, message should be retryable (next_retry_at is in the past)
            retryable = await q.get_retryable()
            assert len(retryable) == 1
            assert retryable[0].message_id == "m1"
            assert retryable[0].retry_count == 1
        finally:
            await q.close()

    async def test_retry_pending_sets_next_retry_at(self, tmp_path):
        q = DeliveryQueue(tmp_path / "test.db")
        await q.open()
        try:
            await q.enqueue(_make_record(message_id="m1"))
            before = time.time()
            await q.retry_pending("m1", retry_delay=60.0)

            # next_retry_at should be ~60 seconds from now
            # Query raw to check next_retry_at
            row = q._db.execute(
                "SELECT next_retry_at, retry_count FROM delivery_queue WHERE message_id = ?",
                ("m1",),
            ).fetchone()
            assert row["retry_count"] == 1
            assert row["next_retry_at"] >= before + 59.0  # allow 1s tolerance
        finally:
            await q.close()

    async def test_get_retryable_returns_past_retry_time_only(self, tmp_path):
        q = DeliveryQueue(tmp_path / "test.db")
        await q.open()
        try:
            await q.enqueue(_make_record(message_id="m1"))
            await q.enqueue(_make_record(message_id="m2"))

            # m1: retry in the past (retryable)
            await q.retry_pending("m1", retry_delay=0.0)
            # m2: retry far in the future (not retryable yet)
            await q.retry_pending("m2", retry_delay=3600.0)

            retryable = await q.get_retryable()
            assert len(retryable) == 1
            assert retryable[0].message_id == "m1"
        finally:
            await q.close()


class TestExpiredForNotification:
    async def test_get_expired_for_notification(self, tmp_path):
        q = DeliveryQueue(tmp_path / "test.db")
        await q.open()
        try:
            old_time = time.time() - 100_000  # created 100k seconds ago
            await q.enqueue(_make_record(message_id="old-msg", created_at=old_time))
            await q.enqueue(_make_record(message_id="new-msg", created_at=time.time()))

            # TTL of 86400 seconds: only old-msg should be "expired"
            expired = await q.get_expired_for_notification(ttl_seconds=86400.0)
            assert len(expired) == 1
            assert expired[0].message_id == "old-msg"
        finally:
            await q.close()


class TestCleanup:
    async def test_cleanup_delivered_removes_old(self, tmp_path):
        q = DeliveryQueue(tmp_path / "test.db")
        await q.open()
        try:
            await q.enqueue(_make_record(message_id="m1"))
            await q.mark_delivered("m1")

            # Manually set delivered_at to 30 days ago
            old_time = time.time() - 30 * 86400
            q._db.execute(
                "UPDATE delivery_queue SET delivered_at = ? WHERE message_id = ?",
                (old_time, "m1"),
            )
            q._db.commit()

            deleted = await q.cleanup_delivered(retention_days=7)
            assert deleted == 1
        finally:
            await q.close()

    async def test_cleanup_delivered_keeps_recent(self, tmp_path):
        q = DeliveryQueue(tmp_path / "test.db")
        await q.open()
        try:
            await q.enqueue(_make_record(message_id="m1"))
            await q.mark_delivered("m1")

            # delivered_at is now (just delivered), retention is 7 days
            deleted = await q.cleanup_delivered(retention_days=7)
            assert deleted == 0
        finally:
            await q.close()

    async def test_cleanup_expired_removes_expired(self, tmp_path):
        q = DeliveryQueue(tmp_path / "test.db")
        await q.open()
        try:
            await q.enqueue(_make_record(message_id="m1"))
            await q.enqueue(_make_record(message_id="m2"))
            await q.mark_expired("m1")

            deleted = await q.cleanup_expired()
            assert deleted == 1

            # m2 should still be pending
            pending = await q.get_pending_for_endpoint("ep-1")
            assert len(pending) == 1
            assert pending[0].message_id == "m2"
        finally:
            await q.close()

    async def test_cleanup_expired_with_no_expired(self, tmp_path):
        q = DeliveryQueue(tmp_path / "test.db")
        await q.open()
        try:
            await q.enqueue(_make_record(message_id="m1"))
            deleted = await q.cleanup_expired()
            assert deleted == 0
        finally:
            await q.close()
