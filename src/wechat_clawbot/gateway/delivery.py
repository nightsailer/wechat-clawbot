"""SQLite-backed delivery queue for gateway messages.

Provides durable, WAL-mode storage for messages awaiting delivery to
upstream endpoints.  All I/O is offloaded to a worker thread via
``anyio.to_thread.run_sync`` so the async event-loop is never blocked.
"""

from __future__ import annotations

import functools
import sqlite3
import time
from typing import TYPE_CHECKING, Any

import anyio

if TYPE_CHECKING:
    from pathlib import Path

from .types import DeliveryRecord, DeliveryStatus

# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS delivery_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT UNIQUE NOT NULL,
    account_id TEXT NOT NULL,
    sender_id TEXT NOT NULL,
    endpoint_id TEXT NOT NULL,
    content TEXT NOT NULL,
    context_token TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at REAL NOT NULL,
    delivered_at REAL,
    retry_count INTEGER DEFAULT 0,
    next_retry_at REAL
);
"""

_CREATE_INDEXES = """\
CREATE INDEX IF NOT EXISTS idx_dq_status ON delivery_queue(status);
CREATE INDEX IF NOT EXISTS idx_dq_endpoint ON delivery_queue(endpoint_id, status);
"""

_INSERT = """\
INSERT INTO delivery_queue
    (message_id, account_id, sender_id, endpoint_id, content,
     context_token, status, created_at, retry_count, next_retry_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_MARK_DELIVERED = """\
UPDATE delivery_queue
   SET status = 'delivered', delivered_at = ?
 WHERE message_id = ?
"""

_MARK_EXPIRED = """\
UPDATE delivery_queue
   SET status = 'expired'
 WHERE message_id = ?
"""

_PENDING_FOR_ENDPOINT = """\
SELECT * FROM delivery_queue
 WHERE endpoint_id = ? AND status = 'pending'
 ORDER BY created_at ASC
"""

_EXPIRED_FOR_NOTIFICATION = """\
SELECT * FROM delivery_queue
 WHERE status = 'pending' AND created_at <= ?
 ORDER BY created_at ASC
"""

_RETRY_PENDING = """\
UPDATE delivery_queue
   SET retry_count = retry_count + 1, next_retry_at = ?
 WHERE message_id = ?
"""

_RETRYABLE = """\
SELECT * FROM delivery_queue
 WHERE status = 'pending' AND next_retry_at IS NOT NULL AND next_retry_at <= ?
 ORDER BY next_retry_at ASC
"""

_CLEANUP_DELIVERED = """\
DELETE FROM delivery_queue
 WHERE status = 'delivered' AND delivered_at <= ?
"""

_CLEANUP_EXPIRED = """\
DELETE FROM delivery_queue
 WHERE status = 'expired'
"""


# ---------------------------------------------------------------------------
# Row → dataclass helper
# ---------------------------------------------------------------------------


def _row_to_record(row: sqlite3.Row) -> DeliveryRecord:
    """Convert a sqlite3.Row to a :class:`DeliveryRecord`."""
    return DeliveryRecord(
        id=row["id"],
        message_id=row["message_id"],
        account_id=row["account_id"],
        sender_id=row["sender_id"],
        endpoint_id=row["endpoint_id"],
        content=row["content"],
        context_token=row["context_token"],
        status=DeliveryStatus(row["status"]),
        created_at=row["created_at"],
        delivered_at=row["delivered_at"] or 0.0,
        retry_count=row["retry_count"] or 0,
        next_retry_at=row["next_retry_at"] or 0.0,
    )


# ---------------------------------------------------------------------------
# DeliveryQueue
# ---------------------------------------------------------------------------


class DeliveryQueue:
    """Async SQLite delivery queue with WAL mode and single-writer pattern.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.  Parent directories are created
        automatically on :meth:`open`.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    # -- lifecycle -----------------------------------------------------------

    async def open(self) -> None:
        """Create the database connection and ensure the schema exists."""
        await anyio.to_thread.run_sync(self._open_sync)

    def _open_sync(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.executescript(_CREATE_TABLE + _CREATE_INDEXES)
        self._conn = conn

    async def close(self) -> None:
        """Close the underlying database connection."""
        if self._conn is not None:
            await anyio.to_thread.run_sync(self._conn.close)
            self._conn = None

    # -- helpers -------------------------------------------------------------

    @property
    def _db(self) -> sqlite3.Connection:
        if self._conn is None:
            msg = "DeliveryQueue is not open — call open() first"
            raise RuntimeError(msg)
        return self._conn

    async def _run(self, fn: functools.partial[Any]) -> Any:
        """Run *fn* in a worker thread."""
        return await anyio.to_thread.run_sync(fn)

    # -- public API ----------------------------------------------------------

    async def enqueue(self, record: DeliveryRecord) -> int:
        """Insert a delivery record and return its auto-generated row ID."""
        return int(
            await self._run(
                functools.partial(
                    self._enqueue_sync,
                    record,
                )
            )
        )

    def _enqueue_sync(self, record: DeliveryRecord) -> int:
        cur = self._db.execute(
            _INSERT,
            (
                record.message_id,
                record.account_id,
                record.sender_id,
                record.endpoint_id,
                record.content,
                record.context_token,
                record.status.value,
                record.created_at or time.time(),
                record.retry_count,
                record.next_retry_at or None,
            ),
        )
        self._db.commit()
        return cur.lastrowid or 0

    async def mark_delivered(self, message_id: str) -> None:
        """Mark a message as delivered with the current timestamp."""
        await self._run(functools.partial(self._mark_delivered_sync, message_id))

    def _mark_delivered_sync(self, message_id: str) -> None:
        self._db.execute(_MARK_DELIVERED, (time.time(), message_id))
        self._db.commit()

    async def mark_expired(self, message_id: str) -> None:
        """Mark a message as expired."""
        await self._run(functools.partial(self._mark_expired_sync, message_id))

    def _mark_expired_sync(self, message_id: str) -> None:
        self._db.execute(_MARK_EXPIRED, (message_id,))
        self._db.commit()

    async def get_pending_for_endpoint(self, endpoint_id: str) -> list[DeliveryRecord]:
        """Return pending messages for *endpoint_id*, oldest first."""
        rows = await self._run(functools.partial(self._get_pending_for_endpoint_sync, endpoint_id))
        return [_row_to_record(r) for r in rows]  # type: ignore[union-attr]

    def _get_pending_for_endpoint_sync(self, endpoint_id: str) -> list[sqlite3.Row]:
        return self._db.execute(_PENDING_FOR_ENDPOINT, (endpoint_id,)).fetchall()

    async def get_expired_for_notification(
        self, ttl_seconds: float = 86400.0
    ) -> list[DeliveryRecord]:
        """Return pending messages older than *ttl_seconds* that need expiry notification."""
        cutoff = time.time() - ttl_seconds
        rows = await self._run(functools.partial(self._get_expired_for_notification_sync, cutoff))
        return [_row_to_record(r) for r in rows]  # type: ignore[union-attr]

    def _get_expired_for_notification_sync(self, cutoff: float) -> list[sqlite3.Row]:
        return self._db.execute(_EXPIRED_FOR_NOTIFICATION, (cutoff,)).fetchall()

    async def retry_pending(self, message_id: str, retry_delay: float = 30.0) -> None:
        """Increment retry count and schedule the next retry attempt."""
        next_retry_at = time.time() + retry_delay
        await self._run(functools.partial(self._retry_pending_sync, message_id, next_retry_at))

    def _retry_pending_sync(self, message_id: str, next_retry_at: float) -> None:
        self._db.execute(_RETRY_PENDING, (next_retry_at, message_id))
        self._db.commit()

    async def get_retryable(self) -> list[DeliveryRecord]:
        """Return pending messages whose next retry time has arrived."""
        now = time.time()
        rows = await self._run(functools.partial(self._get_retryable_sync, now))
        return [_row_to_record(r) for r in rows]  # type: ignore[union-attr]

    def _get_retryable_sync(self, now: float) -> list[sqlite3.Row]:
        return self._db.execute(_RETRYABLE, (now,)).fetchall()

    async def cleanup_delivered(self, retention_days: int = 7) -> int:
        """Delete delivered messages older than *retention_days*.

        Returns the number of rows deleted.
        """
        cutoff = time.time() - (retention_days * 86400)
        count = await self._run(functools.partial(self._cleanup_delivered_sync, cutoff))
        return int(count)  # type: ignore[arg-type]

    def _cleanup_delivered_sync(self, cutoff: float) -> int:
        cur = self._db.execute(_CLEANUP_DELIVERED, (cutoff,))
        self._db.commit()
        return cur.rowcount

    async def cleanup_expired(self) -> int:
        """Delete all expired messages.

        Returns the number of rows deleted.
        """
        count = await self._run(functools.partial(self._cleanup_expired_sync))
        return int(count)  # type: ignore[arg-type]

    def _cleanup_expired_sync(self) -> int:
        cur = self._db.execute(_CLEANUP_EXPIRED)
        self._db.commit()
        return cur.rowcount
