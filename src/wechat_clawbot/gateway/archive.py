"""Message archive — sidecar for complete conversation history.

Provides an async SQLite-backed archive that records every inbound and
outbound message flowing through the gateway.  Used when the ``archive``
section is enabled in ``gateway.yaml``.
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

from .db import AsyncSQLiteStore

logger = logging.getLogger(__name__)

_DIR_INBOUND = "inbound"
_DIR_OUTBOUND = "outbound"

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    direction TEXT NOT NULL,
    account_id TEXT NOT NULL,
    sender_id TEXT NOT NULL,
    endpoint_id TEXT,
    content TEXT NOT NULL,
    timestamp REAL NOT NULL,
    metadata TEXT
);
CREATE INDEX IF NOT EXISTS idx_msg_ts ON messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_msg_sender ON messages(sender_id);
CREATE INDEX IF NOT EXISTS idx_msg_endpoint ON messages(endpoint_id);
"""


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a ``sqlite3.Row`` to a plain dict."""
    return {
        "id": row["id"],
        "direction": row["direction"],
        "account_id": row["account_id"],
        "sender_id": row["sender_id"],
        "endpoint_id": row["endpoint_id"],
        "content": row["content"],
        "timestamp": row["timestamp"],
        "metadata": row["metadata"],
    }


class MessageArchive(AsyncSQLiteStore):
    """Async message archive backed by SQLite.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.  Parent directories are created
        automatically on :meth:`open`.
    """

    def __init__(self, db_path: Path) -> None:
        super().__init__(db_path)

    def _get_schema_sql(self) -> str:
        return _CREATE_TABLE

    # ---- recording -----------------------------------------------------------

    async def record(
        self,
        direction: str,
        account_id: str,
        sender_id: str,
        endpoint_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a message with the given direction."""
        if not self._conn:
            return
        meta_str = json.dumps(metadata) if metadata else None

        def _do() -> None:
            assert self._conn is not None
            self._conn.execute(
                "INSERT INTO messages"
                " (direction, account_id, sender_id, endpoint_id, content, timestamp, metadata)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (direction, account_id, sender_id, endpoint_id, content, time.time(), meta_str),
            )
            self._conn.commit()

        await self._run(_do)  # type: ignore[arg-type]

    async def record_inbound(
        self,
        account_id: str,
        sender_id: str,
        endpoint_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record an inbound (WeChat -> endpoint) message."""
        await self.record(_DIR_INBOUND, account_id, sender_id, endpoint_id, content, metadata)

    async def record_outbound(
        self,
        account_id: str,
        sender_id: str,
        endpoint_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record an outbound (endpoint -> WeChat) message."""
        await self.record(_DIR_OUTBOUND, account_id, sender_id, endpoint_id, content, metadata)

    # ---- querying ------------------------------------------------------------

    async def query(
        self,
        sender_id: str | None = None,
        endpoint_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Query archive messages with optional filters.

        Parameters
        ----------
        sender_id:
            Filter by sender ID.
        endpoint_id:
            Filter by endpoint ID.
        limit:
            Maximum number of records to return.
        offset:
            Number of records to skip (for pagination).

        Returns
        -------
        list[dict]:
            List of message dicts ordered by timestamp descending.
        """
        if not self._conn:
            return []

        conditions: list[str] = []
        params: list[Any] = []

        if sender_id:
            conditions.append("sender_id = ?")
            params.append(sender_id)
        if endpoint_id:
            conditions.append("endpoint_id = ?")
            params.append(endpoint_id)

        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"SELECT * FROM messages{where} ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        def _do() -> list[dict[str, Any]]:
            assert self._conn is not None
            rows = self._conn.execute(sql, params).fetchall()
            return [_row_to_dict(r) for r in rows]

        return await self._run(_do)  # type: ignore[arg-type]

    # ---- maintenance ---------------------------------------------------------

    async def cleanup(self, retention_days: int) -> int:
        """Delete messages older than *retention_days*.

        Returns the number of rows deleted.
        """
        if retention_days <= 0 or not self._conn:
            return 0
        cutoff = time.time() - retention_days * 86400

        def _do() -> int:
            assert self._conn is not None
            cur = self._conn.execute("DELETE FROM messages WHERE timestamp < ?", (cutoff,))
            self._conn.commit()
            return cur.rowcount

        return await self._run(_do)  # type: ignore[arg-type]
