"""Shared async SQLite store base class."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Any

import anyio

if TYPE_CHECKING:
    import functools
    from pathlib import Path


class AsyncSQLiteStore:
    """Base class for async SQLite-backed stores with WAL mode."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._limiter = anyio.CapacityLimiter(1)

    def _get_schema_sql(self) -> str:
        """Subclasses must return their CREATE TABLE + INDEX SQL."""
        raise NotImplementedError

    async def open(self) -> None:
        """Create the database connection and ensure the schema exists."""

        def _open() -> sqlite3.Connection:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.executescript(self._get_schema_sql())
            return conn

        self._conn = await anyio.to_thread.run_sync(_open)

    async def close(self) -> None:
        """Close the underlying database connection."""
        if self._conn is not None:
            conn = self._conn
            self._conn = None
            await anyio.to_thread.run_sync(conn.close, limiter=self._limiter)

    @property
    def _db(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError(f"{type(self).__name__} is not open — call open() first")
        return self._conn

    async def _run(self, fn: functools.partial[Any]) -> Any:
        """Run *fn* in a worker thread, serialized via capacity limiter."""
        return await anyio.to_thread.run_sync(fn, limiter=self._limiter)
