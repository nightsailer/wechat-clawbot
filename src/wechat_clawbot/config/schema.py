"""Pydantic configuration schema (replaces Zod schema from TS)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from wechat_clawbot.auth.accounts import CDN_BASE_URL, DEFAULT_BASE_URL


class WeixinAccountConfig(BaseModel):
    """Per-account config section."""

    name: str | None = None
    enabled: bool | None = None
    base_url: str = Field(default=DEFAULT_BASE_URL, alias="baseUrl")
    cdn_base_url: str = Field(default=CDN_BASE_URL, alias="cdnBaseUrl")
    route_tag: int | None = Field(default=None, alias="routeTag")

    model_config = {"populate_by_name": True}


class WeixinConfigSchema(BaseModel):
    """Top-level weixin config schema (token is stored in credentials, not config)."""

    name: str | None = None
    enabled: bool | None = None
    base_url: str = Field(default=DEFAULT_BASE_URL, alias="baseUrl")
    cdn_base_url: str = Field(default=CDN_BASE_URL, alias="cdnBaseUrl")
    route_tag: int | None = Field(default=None, alias="routeTag")
    accounts: dict[str, WeixinAccountConfig] | None = None
    log_upload_url: str | None = Field(default=None, alias="logUploadUrl")

    model_config = {"populate_by_name": True}


class GatewayModeConfig(BaseModel):
    """Marker for gateway mode detection. See gateway/config.py for full schema."""

    gateway: dict | None = None
