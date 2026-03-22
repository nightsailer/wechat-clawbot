"""Unified CDN URL construction for Weixin CDN upload/download."""

from __future__ import annotations

from urllib.parse import quote


def build_cdn_download_url(encrypted_query_param: str, cdn_base_url: str) -> str:
    """Build a CDN download URL from ``encrypt_query_param``."""
    return f"{cdn_base_url}/download?encrypted_query_param={quote(encrypted_query_param)}"


def build_cdn_upload_url(cdn_base_url: str, upload_param: str, filekey: str) -> str:
    """Build a CDN upload URL from ``upload_param`` and ``filekey``."""
    return (
        f"{cdn_base_url}/upload"
        f"?encrypted_query_param={quote(upload_param)}"
        f"&filekey={quote(filekey)}"
    )
