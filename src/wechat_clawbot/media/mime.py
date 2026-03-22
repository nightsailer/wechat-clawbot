"""MIME type <-> file extension mapping."""

from __future__ import annotations

import os
from urllib.parse import urlparse

EXTENSION_TO_MIME: dict[str, str] = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".zip": "application/zip",
    ".tar": "application/x-tar",
    ".gz": "application/gzip",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}

MIME_TO_EXTENSION: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
    "video/x-matroska": ".mkv",
    "video/x-msvideo": ".avi",
    "audio/mpeg": ".mp3",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "application/pdf": ".pdf",
    "application/zip": ".zip",
    "application/x-tar": ".tar",
    "application/gzip": ".gz",
    "text/plain": ".txt",
    "text/csv": ".csv",
}


def get_mime_from_filename(filename: str) -> str:
    """Get MIME type from filename extension. Returns ``application/octet-stream`` for unknown."""
    _, ext = os.path.splitext(filename)
    return EXTENSION_TO_MIME.get(ext.lower(), "application/octet-stream")


def get_extension_from_mime(mime_type: str) -> str:
    """Get file extension from MIME type. Returns ``.bin`` for unknown types."""
    ct = mime_type.split(";")[0].strip().lower()
    return MIME_TO_EXTENSION.get(ct, ".bin")


def get_extension_from_content_type_or_url(content_type: str | None, url: str) -> str:
    """Get file extension from Content-Type header or URL path."""
    if content_type:
        ext = get_extension_from_mime(content_type)
        if ext != ".bin":
            return ext
    try:
        parsed = urlparse(url)
        _, ext = os.path.splitext(parsed.path)
        ext = ext.lower()
        if ext in EXTENSION_TO_MIME:
            return ext
    except Exception:
        pass
    return ".bin"
