# CLAUDE.md

Project: **wechat-clawbot** — WeChat iLink Bot SDK with multi-endpoint gateway for AI backends.

> **WeChat Bot Constraint:** Each WeChat account can create only one Bot, and that Bot is exclusively bound to the creator's WeChat account (1:1). Multiple people cannot share a single Bot. The gateway manages multiple Bots (each from a different WeChat user) routing to multiple endpoints.

## Architecture

Two operating modes:

- **Channel Mode** (`claude_channel/`) — single-user MCP bridge connecting one WeChat account to one Claude Code session
- **Gateway Mode** (`gateway/`) — multi-Bot, multi-endpoint routing gateway: multiple WeChat Bot accounts (each 1:1 bound to its creator's WeChat account) route messages to multiple upstream AI endpoints (MCP SSE, SDK WebSocket, HTTP Webhook)

## Key Directories

```
src/wechat_clawbot/
  api/              ilink HTTP API client (getUpdates, sendMessage, getConfig, sendTyping)
  auth/             QR login, account storage, credential management
  cdn/              AES-128-ECB CDN upload/download pipeline
  claude_channel/   Claude Code MCP Channel bridge (CLI + server)
  config/           Pydantic configuration schema
  gateway/          Multi-Bot, multi-endpoint routing gateway
    channels/       Sub-channel implementations (MCP SSE, SDK WebSocket, HTTP Webhook)
    admin.py        Admin HTTP API (Starlette, Bearer auth)
    app.py          Main gateway orchestrator (GatewayApp)
    cli.py          CLI entry point (clawbot-gateway, 25+ subcommands)
    config.py       gateway.yaml schema (GatewayConfig, Pydantic)
    delivery.py     SQLite-backed delivery queue
    router.py       Message routing engine (active-endpoint, @mention, /command)
    session.py      User session store with file persistence
    endpoint_manager.py  Endpoint registry with health tracking
    invite.py       Invite code system
    auth.py         Authorization module (allowlist/open/invite-code)
    archive.py      Message archive sidecar (SQLite)
    db.py           AsyncSQLiteStore base class
    types.py        Core dataclasses and enums
  media/            Media download, MIME types, SILK transcoding
  messaging/        Inbound conversion, send pipeline, slash commands
  monitor/          Long-poll monitor loop
  sdk/              ClawBotClient library for custom bots (WebSocket)
  storage/          State directory, sync buffer persistence
  util/             Logger, ID generation, sensitive field redaction
```

## Testing

```bash
uv run pytest tests/                # run all tests
uv run pytest tests/ -v             # verbose
uv run pytest tests/test_gateway.py # single file
```

## Linting and Formatting

```bash
uv run ruff check src/ --fix               # lint with auto-fix
uv run ruff format src/                    # format
uv run ruff check src/ tests/ && uv run ruff format src/ tests/  # full check
```

## Key Conventions

- **Async/await with anyio** — all I/O uses anyio (not raw asyncio) for structured concurrency
- **Pydantic for configuration** — all config models use Pydantic v2 with validation
- **Dataclasses for runtime types** — `types.py` uses `@dataclass` for runtime data structures
- **SQLite with WAL mode** — delivery queue and archive use WAL-mode SQLite via `AsyncSQLiteStore`
- **Thread offloading** — SQLite operations run in worker threads via `anyio.to_thread.run_sync` with capacity limiters
- **Starlette for HTTP** — gateway and admin API use Starlette ASGI
- **No markdown in WeChat replies** — gateway command responses use plain text (WeChat does not render markdown)
- **Ruff for linting** — configured in `pyproject.toml`, target Python 3.10+
