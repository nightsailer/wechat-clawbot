"""Plugin logger — writes JSON lines to ``/tmp/openclaw/openclaw-YYYY-MM-DD.log``."""

from __future__ import annotations

import json
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

MAIN_LOG_DIR = Path("/tmp/openclaw")
SUBSYSTEM = "gateway/channels/openclaw-weixin"
RUNTIME = "python"
RUNTIME_VERSION = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
HOSTNAME = socket.gethostname() or "unknown"
PARENT_NAMES = ["openclaw"]

LEVEL_IDS: dict[str, int] = {
    "TRACE": 1,
    "DEBUG": 2,
    "INFO": 3,
    "WARN": 4,
    "ERROR": 5,
    "FATAL": 6,
}

_DEFAULT_LOG_LEVEL = "INFO"
_min_level_id: int = LEVEL_IDS.get(
    os.environ.get("OPENCLAW_LOG_LEVEL", "").upper(), LEVEL_IDS[_DEFAULT_LOG_LEVEL]
)
_log_dir_ensured = False


def set_log_level(level: str) -> None:
    """Dynamically change the minimum log level at runtime."""
    global _min_level_id
    upper = level.upper()
    if upper not in LEVEL_IDS:
        raise ValueError(f"Invalid log level: {level}. Valid: {', '.join(LEVEL_IDS)}")
    _min_level_id = LEVEL_IDS[upper]


def _to_local_iso(now: datetime) -> str:
    """Render *now* as a local-time ISO string with timezone offset."""
    local = now.astimezone()
    return local.isoformat()


def _local_date_key(now: datetime) -> str:
    return now.astimezone().strftime("%Y-%m-%d")


def _resolve_main_log_path() -> Path:
    date_key = _local_date_key(datetime.now(timezone.utc))
    return MAIN_LOG_DIR / f"openclaw-{date_key}.log"


def _write_log(level: str, message: str, account_id: str | None = None) -> None:
    global _log_dir_ensured
    level_id = LEVEL_IDS.get(level, LEVEL_IDS["INFO"])
    if level_id < _min_level_id:
        return

    now = datetime.now(timezone.utc)
    logger_name = f"{SUBSYSTEM}/{account_id}" if account_id else SUBSYSTEM
    prefixed = f"[{account_id}] {message}" if account_id else message

    entry = json.dumps(
        {
            "0": logger_name,
            "1": prefixed,
            "_meta": {
                "runtime": RUNTIME,
                "runtimeVersion": RUNTIME_VERSION,
                "hostname": HOSTNAME,
                "name": logger_name,
                "parentNames": PARENT_NAMES,
                "date": now.isoformat(),
                "logLevelId": level_id,
                "logLevelName": level,
            },
            "time": _to_local_iso(now),
        },
        ensure_ascii=False,
    )

    try:
        if not _log_dir_ensured:
            MAIN_LOG_DIR.mkdir(parents=True, exist_ok=True)
            _log_dir_ensured = True
        with _resolve_main_log_path().open("a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except Exception:
        pass  # best-effort


class Logger:
    """Structured JSON-line logger, compatible with tslog format."""

    def __init__(self, account_id: str | None = None) -> None:
        self._account_id = account_id

    def info(self, message: str) -> None:
        _write_log("INFO", message, self._account_id)

    def debug(self, message: str) -> None:
        _write_log("DEBUG", message, self._account_id)

    def warning(self, message: str) -> None:
        _write_log("WARN", message, self._account_id)

    # Alias kept for compatibility with existing call sites.
    warn = warning

    def error(self, message: str) -> None:
        _write_log("ERROR", message, self._account_id)

    def with_account(self, account_id: str) -> Logger:
        """Return a child logger whose messages are prefixed with ``[account_id]``."""
        return Logger(account_id)

    def get_log_file_path(self) -> str:
        return str(_resolve_main_log_path())

    def close(self) -> None:
        pass  # no persistent handle


logger = Logger()
