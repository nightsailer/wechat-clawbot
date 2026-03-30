"""Filesystem utilities."""

from __future__ import annotations

import contextlib
import os
import tempfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def atomic_write_text(path: Path, text: str) -> None:
    """Write text to *path* atomically using a temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        os.write(fd, text.encode("utf-8"))
        os.close(fd)
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.close(fd)
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
