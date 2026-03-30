# Changelog

All notable changes to this project will be documented in this file.

## [0.4.0] - 2026-03-30

Gateway v2 — multi-Bot, multi-endpoint message routing gateway for WeChat ClawBot.

### Added

- **Gateway mode with multi-Bot, multi-endpoint routing** — multiple WeChat Bot accounts (each 1:1 bound to its creator's WeChat account) map to multiple upstream AI endpoints, with per-Bot-owner session isolation and endpoint switching
- **Three sub-channel types** — MCP SSE (`/mcp/{id}/sse`), SDK WebSocket (`/sdk/{id}/ws`), and HTTP Webhook (`/http/{id}/callback`) for connecting different backend types
- **Delivery queue with SQLite persistence** — WAL-mode SQLite-backed durable queue with retry logic and expiry; no messages lost on restart
- **Message archive (sidecar)** — optional SQLite-backed archive recording every inbound/outbound message with retention policy support
- **Session management** — per-user state persistence with active endpoint tracking, endpoint bindings, and per-endpoint session context
- **Authorization system** — three modes: `allowlist` (admin-only), `open` (everyone), `invite-code` (code-gated access); admin role with elevated privileges
- **Router engine** — resolves messages via active-endpoint, `@mention` prefix routing, or `/command` gateway commands; configurable prefix and command characters
- **Endpoint manager** — runtime registry of upstream endpoints with online/offline status tracking and health checks
- **Admin HTTP API** — separate Starlette server on `admin_port` with Bearer token auth; endpoints for status, accounts, endpoints, users, and invite management
- **Invite code system** — generate short-lived, usage-limited codes for endpoint binding; file-backed storage with TTL and max-uses
- **Gateway CLI (`clawbot-gateway`)** — full command-line interface with 25+ subcommands: `init`, `start`, `stop`, `status`, `account {add,list,remove,status}`, `user {list,info,allow,block,bind,unbind}`, `endpoint {list,add,remove}`, `invite {list,create}`, `logs`
- **SDK client library (`ClawBotClient`)** — async WebSocket client with auto-reconnect for building custom bots; `Message` dataclass, `messages()` async iterator, `reply()` method
- **WeChat gateway commands** — `/list`, `/use <name>`, `/to <name> <msg>`, `/status`, `/bind`, `/unbind`, `/help` for in-chat endpoint management
- **Shared utilities** — `AsyncSQLiteStore` base class, `poll_core` shared polling logic, `mcp_defs` MCP notification constants, `atomic_write_text` for safe file writes
- **Gateway Pydantic config** — full `gateway.yaml` schema with validation: `GatewayConfig`, `GatewayServerConfig`, `AccountConfigModel`, `EndpointConfigModel`, `RoutingConfig`, `AuthorizationConfig`, `ArchiveConfig`
- 308 new tests covering all gateway modules (102 → 410 total)

### Changed

- Project description updated to reflect gateway capability
- `pyproject.toml` now declares `clawbot-gateway` CLI entry point

## [0.3.0] - 2026-03-29

Synced with upstream `@tencent-weixin/openclaw-weixin` v2.1.1.

### Added

- **CDN full_url support** — server can now return complete download/upload URLs directly; client falls back to URL construction when `full_url` is absent (`ENABLE_CDN_URL_FALLBACK` flag)
- **Context token disk persistence** — tokens survive process restarts via `{accountId}.context-tokens.json`; `set_context_token` skips disk I/O when token is unchanged
- **iLink protocol headers** — all requests now include `iLink-App-Id` and `iLink-App-ClientVersion` headers
- **QR login IDC redirect** — new `scaned_but_redirect` status with `redirect_host` for cross-datacenter routing
- **Sensitive field redaction** — `redact_body()` masks `context_token`, `bot_token`, `token`, `authorization` values before logging
- **Account cleanup** — `clear_stale_accounts_for_user_id()` removes stale accounts after re-login; `clear_weixin_account()` now removes all associated files (`.json`, `.sync.json`, `.context-tokens.json`)
- **`ApiHttpError` exception** — structured HTTP error with `status_code` attribute, replacing stringly-typed RuntimeError matching
- **`api_get_fetch()`** — GET request wrapper with common iLink headers
- **`CDNMedia.has_download_source`** — property to check if media has `encrypt_query_param` or `full_url`
- **QR code browser fallback** — prints URL when terminal QR rendering fails
- **routeTag config caching** — `load_config_route_tag()` caches result after first read
- 37 new tests covering context token persistence, CDN URL routing, version encoding, and sensitive field redaction (65 → 102 total)

### Changed

- **contextToken soft-fail** — send functions now warn instead of raising when `context_token` is absent; server accepts messages without it since iLink v2.1+
- **Error notice behavior** — `send_weixin_error_notice()` now attempts to send even without `context_token` (previously was a no-op)
- **QR login networking** — uses fixed base URL `https://ilinkai.weixin.qq.com` for QR requests; network/gateway errors (502/503/504/524) treated as retryable instead of fatal
- **`_poll_qr_status` exception handling** — narrowed from catch-all `Exception` to `httpx.TimeoutException/ConnectError/NetworkError` + `ApiHttpError` with gateway status code check
- **`channel_version` in `base_info`** — now sends upstream version `2.1.1` instead of Python package version
- **`setup.py`** — replaced removed `close_login_client()` with `close_shared_client()` from `api.client`

### Fixed

- **`setup.py` ImportError** — `close_login_client` was removed but still imported, breaking `wechat-clawbot-cc setup`
- **Empty QR URL output** — else branch no longer prints empty `qrcode_url`, shows error message instead
- **TOCTOU patterns** — `restore_context_tokens`, `clear_context_tokens_for_account`, `_load_route_tag_section` replaced `exists()` → operate with EAFP pattern
- **`restore_context_tokens` error handling** — separated `FileNotFoundError`, `JSONDecodeError`, and type validation into distinct branches with appropriate log levels

### Removed

- `close_login_client()` — login now uses the shared API client
- `logUploadUrl` config field — removed upstream

## [0.2.0] - 2026-03-22

### Added

- `wechat_send_file` tool — send images, videos, and documents via CDN upload
- `wechat_typing` tool — typing indicator with keepalive
- iLink Bot Protocol documentation (`docs/ilink-protocol.md`)
- CI and PyPI publish GitHub Actions workflows

### Changed

- Migrated from `asyncio` to `anyio` for structured concurrency
- Added `anyio` as explicit dependency
- SOCKS proxy support via `httpx[socks]` optional extra

## [0.1.0] - 2026-03-22

### Added

- Initial Python port of `@tencent-weixin/openclaw-weixin` v1.0.2
- Full ilink API client (getUpdates, sendMessage, getConfig, sendTyping)
- Multi-account QR code login and credential storage
- AES-128-ECB encrypted CDN upload/download pipeline
- SILK voice transcoding (optional)
- Message processing pipeline with slash commands and debug mode
- Claude Code MCP Channel bridge (`wechat-clawbot-cc` CLI)
- `wechat_reply` MCP tool for sending text replies
