# wechat-clawbot

[中文版](README.zh.md) | English

WeChat iLink Bot SDK with multi-user gateway for AI backends (Claude Code, Codex, custom bots).

Ported from [@tencent-weixin/openclaw-weixin](https://www.npmjs.com/package/@tencent-weixin/openclaw-weixin) (TypeScript), synced with upstream v2.1.1.

Two operating modes:

- **Channel Mode** — single-user, single-endpoint MCP bridge for Claude Code
- **Gateway Mode** (v0.4.0+) — M:N multi-user, multi-endpoint routing gateway

> **New to this project?** Read the [Usage Guide](docs/guide.md) for step-by-step scenarios covering deployment, daily operations, SDK development, and more.

```
                          ┌─────────────────────────────────────────────┐
Channel Mode:             │  WeChat ──> ilink API ──> [bridge] ──> Claude Code  │
                          └─────────────────────────────────────────────┘

                          ┌─────────────────────────────────────────────┐
                          │           ┌──> MCP SSE ──> Claude Code      │
Gateway Mode:             │  WeChat ──┤──> SDK WS  ──> Custom Bot       │
                          │   (M:N)   └──> HTTP    ──> Webhook Service  │
                          └─────────────────────────────────────────────┘
```

## Features

- **Full ilink API client** — getUpdates long-poll, sendMessage, getConfig, sendTyping, with `iLink-App-Id` / `iLink-App-ClientVersion` protocol headers
- **Multi-account support** — QR code login with IDC redirect, credential storage, stale account cleanup
- **Media pipeline** — AES-128-ECB encrypted CDN upload/download with `full_url` direct-URL support, image/video/file/voice
- **Context token persistence** — survives process restarts, disk-backed with change detection
- **SILK transcoding** — voice message to WAV conversion (optional)
- **Message processing** — inbound conversion, slash commands, debug mode, error notices
- **Claude Code Channel** — MCP server bridging WeChat messages into Claude Code sessions
- **Gateway mode** — M:N routing gateway with delivery queue, session management, admin API, and SDK client library
- **Secure logging** — automatic redaction of sensitive fields (tokens, authorization) in log output
- **Async-first** — built on httpx + anyio with shared connection pools

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Installation

```bash
uv add wechat-clawbot
```

Or with pip:

```bash
pip install wechat-clawbot
```

Optional extras:

```bash
uv add "wechat-clawbot[gateway]"  # Gateway mode (+pyyaml, uvicorn)
uv add "wechat-clawbot[sdk]"      # SDK client (+websockets)
uv add "wechat-clawbot[silk]"     # SILK voice transcoding
uv add "wechat-clawbot[socks]"    # SOCKS proxy support
```

| Extra | Dependencies | Use case |
|-------|-------------|----------|
| Core (no extra) | anyio, httpx, pydantic, cryptography, qrcode, mcp | Channel mode (Claude Code) |
| `[gateway]` | +pyyaml, uvicorn | Gateway mode (clawbot-gateway CLI) |
| `[sdk]` | +websockets | SDK client (ClawBotClient) |
| `[silk]` | +graiax-silkcoder | SILK voice transcoding |
| `[socks]` | +httpx[socks] | SOCKS proxy support |

## Channel Mode (Single-User)

### Quick Start — Claude Code Channel

### 1. Login with WeChat QR code

```bash
wechat-clawbot-cc setup
```

Scan the terminal QR code with WeChat. Credentials are saved to `~/.claude/channels/wechat/account.json`.

### 2. Register the MCP server

```bash
claude mcp add wechat -- wechat-clawbot-cc serve
```

### 3. Start Claude Code with the WeChat channel

```bash
claude --dangerously-load-development-channels server:wechat
```

Send a message in WeChat ClawBot, and Claude will reply.

### Bridge Mode (via Gateway)

If you already have a running Gateway, use bridge mode instead of direct QR login. The bridge connects to the Gateway's SSE endpoint and forwards WeChat messages to your AI client.

**Claude Code with bridge mode:**

```bash
# Register MCP server in bridge mode
claude mcp add wechat -- wechat-clawbot-cc serve --gateway http://localhost:8765 --endpoint my-project

# Start Claude Code with WeChat channel
claude --dangerously-load-development-channels server:wechat
```

WeChat messages are pushed into the Claude Code session via `notifications/claude/channel`. Claude replies using the `wechat_reply` tool.

**Codex with bridge mode:**

```bash
# Register MCP server in bridge mode
codex mcp add wechat -- wechat-clawbot-cc serve --gateway http://localhost:8765 --endpoint my-project
```

Codex does not support channel push. The bridge adapts via:
- Sends `notifications/resources/updated` when new messages arrive
- Codex calls `wechat_get_messages` tool to fetch pending messages
- Codex calls `wechat_reply` tool to send replies

**Bridge mode flags:**

| Flag | Description |
|------|-------------|
| `--gateway <url>` | Gateway URL (e.g. `http://localhost:8765`) |
| `--endpoint <id>` | Endpoint ID in the gateway (required) |
| `--api-key <key>` | Gateway auth key (optional, matches gateway admin_token) |

**Direct single-user mode is unaffected** — omitting `--gateway` works exactly as before.

## Quick Start — Python SDK

```python
import asyncio
from wechat_clawbot.api.client import WeixinApiOptions, get_updates, send_message
from wechat_clawbot.api.types import (
    MessageType, MessageState, MessageItemType,
    SendMessageReq, WeixinMessage, MessageItem, TextItem,
)

async def main():
    opts = WeixinApiOptions(base_url="https://ilinkai.weixin.qq.com", token="your-bot-token")

    # Long-poll for messages
    resp = await get_updates(base_url=opts.base_url, token=opts.token)
    for msg in resp.msgs or []:
        print(f"From: {msg.from_user_id}, Text: {msg.item_list}")

    # Send a reply
    await send_message(opts, SendMessageReq(msg=WeixinMessage(
        to_user_id="user@im.wechat",
        client_id="my-client-id",
        message_type=MessageType.BOT,
        message_state=MessageState.FINISH,
        item_list=[MessageItem(type=MessageItemType.TEXT, text_item=TextItem(text="Hello!"))],
        context_token="token-from-getupdates",
    )))

asyncio.run(main())
```

## Gateway Mode (v0.4.0+)

The gateway provides M:N routing: multiple WeChat Bot accounts can route messages to multiple upstream AI endpoints. Each user independently selects, switches, and binds endpoints via in-chat commands.

### Architecture

- **Accounts** (downstream) — one or more WeChat Bot accounts, each polling ilink API
- **Endpoints** (upstream) — AI backends connected via MCP SSE, SDK WebSocket, or HTTP webhook
- **Router** — resolves each inbound message to an endpoint based on active selection, `@mention`, or `/command`
- **Session store** — per-user state (active endpoint, bindings, context tokens) persisted to disk
- **Delivery queue** — SQLite-backed durable queue with retry logic
- **Admin API** — separate HTTP server with Bearer token auth for management

### Quick Start

```bash
# 1. Initialize configuration
clawbot-gateway init

# 2. Add a WeChat Bot account (scans QR code)
clawbot-gateway account add

# 3. Edit ~/.clawbot-gateway/gateway.yaml to configure endpoints

# 4. Start the gateway
clawbot-gateway start
```

### Configuration Example

```yaml
# ~/.clawbot-gateway/gateway.yaml
gateway:
  host: 0.0.0.0
  port: 8765
  admin_port: 8766
  admin_token: "your-secret-token"
  log_level: info

accounts:
  main-bot:
    credentials: ~/.clawbot-gateway/accounts/main-bot.json

endpoints:
  claude:
    name: "Claude Code"
    type: mcp            # MCP clients connect to gateway SSE
  my-bot:
    name: "My Bot"
    type: sdk            # SDK clients connect via WebSocket
  webhook-service:
    name: "Webhook"
    type: http           # Gateway POSTs messages to this URL
    url: "https://example.com/webhook"
    api_key: "optional-bearer-token"

routing:
  strategy: active-endpoint   # also: prefix, smart
  mention_prefix: "@"
  gateway_commands: ["/"]     # prefix(es) that trigger gateway commands

authorization:
  mode: allowlist             # also: open, invite-code
  default_endpoints: []       # endpoints auto-bound to new users
  admins: ["admin-user-id@im.wechat"]

archive:
  enabled: false
  path: ~/.clawbot-gateway/archive.db
  retention_days: 0           # 0 = keep forever
```

### WeChat Commands

Users interact with the gateway through in-chat commands:

| Command | Description |
|---------|-------------|
| `/list` | List available endpoints |
| `/use <name>` | Switch active endpoint |
| `/to <name> <message>` | Send one-off message to a specific endpoint |
| `/status` | Show current session status |
| `/bind <name>` | Bind to an endpoint |
| `/unbind <name>` | Unbind from an endpoint |
| `/help` | Show help message |
| `/admin` | Show system info (admin only) |

### Sub-Channel Types

| Type | Transport | Direction | Use Case |
|------|-----------|-----------|----------|
| `mcp` | SSE + JSON-RPC | Client connects to gateway (`/mcp/{id}/sse`) | Claude Code / MCP-compatible clients |
| `sdk` | WebSocket | Client connects to gateway (`/sdk/{id}/ws`) | Custom bots using `ClawBotClient` SDK |
| `http` | Webhook POST | Gateway POSTs to endpoint URL; endpoint callbacks via `/http/{id}/callback` | Third-party services, n8n, Zapier |

### SDK Client Example

```python
import asyncio
from wechat_clawbot.sdk import ClawBotClient

async def main():
    async with ClawBotClient(
        gateway_url="http://localhost:8765",
        endpoint_id="my-bot",
    ) as client:
        async for msg in client.messages():
            print(f"From {msg.sender_id}: {msg.text}")
            await client.reply(msg.sender_id, f"Echo: {msg.text}")

asyncio.run(main())
```

### Admin API

The admin API runs on `admin_port` (default 8766), protected by Bearer token when `admin_token` is set.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/status` | Gateway status overview |
| GET | `/api/accounts` | List Bot accounts |
| GET | `/api/endpoints` | List endpoints with status |
| POST | `/api/endpoints` | Add an endpoint |
| DELETE | `/api/endpoints/{id}` | Remove an endpoint |
| GET | `/api/users` | List users |
| POST | `/api/users/{id}/bind` | Bind user to endpoint |
| POST | `/api/users/{id}/unbind` | Unbind user from endpoint |
| GET | `/api/invites` | List invite codes |
| POST | `/api/invites` | Create invite code |

### CLI Reference

| Command | Description |
|---------|-------------|
| `clawbot-gateway init` | Initialize configuration |
| `clawbot-gateway start` | Start the gateway |
| `clawbot-gateway stop` | Stop the gateway |
| `clawbot-gateway status` | Show gateway status |
| `clawbot-gateway account add` | Add Bot account via QR login |
| `clawbot-gateway account list` | List configured accounts |
| `clawbot-gateway account remove <id>` | Remove an account |
| `clawbot-gateway account status [id]` | Show account status |
| `clawbot-gateway endpoint list` | List endpoints |
| `clawbot-gateway endpoint add <id> [--name NAME] [--type TYPE] [--url URL]` | Add an endpoint |
| `clawbot-gateway endpoint remove <id>` | Remove an endpoint |
| `clawbot-gateway user list` | List all users |
| `clawbot-gateway user info <id>` | Show user info |
| `clawbot-gateway user allow <id>` | Add user to allowlist |
| `clawbot-gateway user block <id>` | Block a user |
| `clawbot-gateway user bind <uid> <eid>` | Bind user to endpoint |
| `clawbot-gateway user unbind <uid> <eid>` | Unbind user from endpoint |
| `clawbot-gateway invite list` | List active invite codes |
| `clawbot-gateway invite create <eid> [--max-uses N] [--ttl HOURS]` | Create invite code |
| `clawbot-gateway logs [-n LINES] [--endpoint ID] [--user ID]` | View message archive |

All commands support `--json` for machine-readable output, `--gateway <url>` for remote management, `--admin-token <token>` for admin API authentication, and `--config <path>` for specifying the gateway.yaml path.

**Environment variables:**

| Variable | Description |
|----------|-------------|
| `CLAWBOT_GATEWAY_URL` | Default gateway admin URL (alternative to `--gateway`) |
| `CLAWBOT_ADMIN_TOKEN` | Default admin Bearer token (alternative to `--admin-token`) |
| `CLAWBOT_GATEWAY_CONFIG` | Path to `gateway.yaml` (alternative to `--config`) |

## Project Structure

```
src/wechat_clawbot/
  api/              # ilink HTTP API client and protocol types
  auth/             # QR login, account storage, pairing
  cdn/              # AES-128-ECB crypto, CDN upload/download
  config/           # Pydantic configuration schema
  media/            # Media download, MIME types, SILK transcoding
  messaging/        # Inbound conversion, send, slash commands, process pipeline
  monitor/          # Long-poll monitor loop
  storage/          # State directory, sync buffer persistence
  util/             # Logger, ID generation, redaction
  claude_channel/   # Claude Code MCP Channel bridge (CLI + server)
  gateway/          # M:N routing gateway (v0.4.0+)
    channels/       #   Sub-channel implementations (MCP, SDK, HTTP)
    admin.py        #   Admin HTTP API server
    app.py          #   Main gateway orchestrator
    cli.py          #   CLI entry point (clawbot-gateway)
    config.py       #   gateway.yaml schema and loader
    delivery.py     #   SQLite-backed delivery queue
    router.py       #   Message routing engine
    session.py      #   User session/state persistence
    endpoint_manager.py  # Endpoint registry with health tracking
    invite.py       #   Invite code system
    auth.py         #   Authorization module (allowlist/open/invite-code)
    archive.py      #   Message archive sidecar (SQLite)
    types.py        #   Core dataclasses and enums
  sdk/              # ClawBotClient library for custom bots
```

## Development

```bash
git clone https://github.com/nightsailer/wechat-clawbot.git
cd wechat-clawbot
uv sync

# Run tests
uv run pytest tests/ -v

# Lint
uv run ruff check src/ tests/

# Format
uv run ruff format src/ tests/
```

## Documentation

- **[Usage Guide](docs/guide.md)** — Scenario-based guide: deployment, team setup, SDK development, webhook integration, maintenance, and troubleshooting
- [Python SDK API](docs/api.md) — Public API reference for wechat-clawbot
- [iLink Bot Protocol](docs/ilink-protocol.md) — WeChat ClawBot iLink API protocol reference

## License

MIT
