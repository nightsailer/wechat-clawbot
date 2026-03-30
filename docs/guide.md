# WeChat ClawBot Usage Guide

[中文版](guide.zh.md) | English

Practical, scenario-based guide for deploying and operating WeChat ClawBot. Organized by who you are and what you want to do.

---

## Scenario 1: Single Developer — Claude Code + WeChat

The simplest setup: you are a solo developer who wants Claude Code to receive and reply to WeChat messages.

### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- A WeChat account with access to the ClawBot iLink platform
- Claude Code CLI installed (`npm install -g @anthropic-ai/claude-code`)

### Step 1: Install wechat-clawbot

```bash
pip install wechat-clawbot
# or with uv:
uv add wechat-clawbot
```

No extra dependencies needed for this scenario — the core package includes everything for Channel Mode.

### Step 2: Login with WeChat QR Code

```bash
wechat-clawbot-cc setup
```

A QR code will appear in your terminal. Open WeChat on your phone and scan it. After authentication, credentials are saved to `~/.claude/channels/wechat/account.json`.

### Step 3: Register the MCP Server

```bash
claude mcp add wechat -- wechat-clawbot-cc serve
```

This tells Claude Code that there is an MCP server called "wechat" that it can connect to.

### Step 4: Start Claude Code with the WeChat Channel

```bash
claude --dangerously-load-development-channels server:wechat
```

Claude Code starts and begins listening for WeChat messages. When someone sends a message to your ClawBot, Claude will see it and can reply using the `wechat_reply` tool.

### Verifying It Works

1. Open WeChat and find the ClawBot conversation
2. Send a test message, e.g. "Hello"
3. In the Claude Code terminal, you should see the message appear as a channel notification
4. Claude will reply, and the response appears in your WeChat chat

### Available Tools in Claude Code

Once connected, Claude Code has access to three tools:

| Tool | Description |
|------|-------------|
| `wechat_reply` | Send a text reply to a WeChat user |
| `wechat_send_file` | Send a file (image, video, document) to a WeChat user |
| `wechat_typing` | Show a typing indicator to a WeChat user |

### Common Issues

| Problem | Solution |
|---------|----------|
| QR code expired | Re-run `wechat-clawbot-cc setup` |
| "No credentials found" | Run `wechat-clawbot-cc setup` before `serve` |
| No messages appearing | Make sure you started Claude Code with `--dangerously-load-development-channels server:wechat` |
| Messages stop arriving | Session may have expired; re-run `wechat-clawbot-cc setup` |

---

## Scenario 2: Single Developer — Codex + WeChat

Same goal as Scenario 1, but using OpenAI Codex instead of Claude Code.

### Differences from Claude Code

Codex does not support MCP channel push notifications. Instead, the bridge adapter uses a polling mechanism:

1. When a new message arrives, the bridge sends a `notifications/resources/updated` notification to Codex
2. Codex calls the `wechat_get_messages` tool to fetch pending messages
3. Codex calls `wechat_reply` to send responses

### Setup (Direct Mode)

```bash
# Install
pip install wechat-clawbot

# Login
wechat-clawbot-cc setup

# Register MCP server for Codex
codex mcp add wechat -- wechat-clawbot-cc serve
```

### Setup (Bridge Mode via Gateway)

If you have a running gateway (see Scenario 3), use bridge mode:

```bash
codex mcp add wechat -- wechat-clawbot-cc serve --gateway http://localhost:8765 --endpoint my-project
```

### How `wechat_get_messages` Works

This tool is automatically available in bridge mode. When called, it drains all pending messages from the queue and returns them in channel-tagged format:

```xml
<channel source="wechat" sender="user123@im.wechat" sender_id="user123@im.wechat">
Hello, can you help me?
</channel>
```

To get Codex to check for messages, include instructions in your prompt like:

> "When you receive a resource update notification for wechat://messages/pending, call wechat_get_messages to check for new WeChat messages."

### Available Tools

All tools from Scenario 1, plus:

| Tool | Description |
|------|-------------|
| `wechat_get_messages` | Drain and return all pending WeChat messages (bridge mode only) |

---

## Scenario 3: Team Setup — Gateway + Multiple AI Backends

> **WeChat Bot Constraint:** Each WeChat account can create only one Bot, and that Bot is exclusively bound to the creator's WeChat account (1:1). Multiple people cannot share a single Bot. The gateway manages multiple Bots (each from a different WeChat user) routing to multiple endpoints.

You are setting up a gateway to route messages from one or more WeChat Bot accounts to multiple AI backends. Each Bot is owned by a different WeChat user. Developers connect their own Claude Code or Codex instance to the gateway as separate endpoints.

### Planning

Before you start, decide on:

- **How many WeChat Bot accounts?** Each WeChat account can only create one Bot (1:1 binding). A single person managing multiple project endpoints needs just one Bot. For team collaboration, each team member needs their own Bot (one WeChat account = one Bot).
- **What endpoints?** Name them after projects or team members (e.g., `project-alpha`, `alice-claude`, `support-bot`).
- **Access control:** Who can use the bot? Options are `open` (anyone), `allowlist` (pre-approved users only), or `invite-code` (users redeem a code to gain access).
- **Server:** The gateway pulls messages from WeChat via long-polling (outbound connection only) — WeChat does not need to reach the gateway. The gateway just needs: internet access (to call the iLink API) and developer access to its ports (for SSE/WebSocket endpoints).

### Step 1: Install and Initialize

On your server:

```bash
pip install "wechat-clawbot[gateway]"

clawbot-gateway init
```

This creates `~/.clawbot-gateway/gateway.yaml` with a template configuration.

### Step 2: Add a WeChat Bot Account

```bash
clawbot-gateway account add
```

Scan the QR code with WeChat. Credentials are saved to `~/.clawbot-gateway/accounts/<account-id>.json`.

### Step 3: Configure the Gateway

Edit `~/.clawbot-gateway/gateway.yaml`:

```yaml
# ---- Server ----------------------------------------------------------------
gateway:
  host: 0.0.0.0          # Listen on all interfaces
  port: 8765              # Main gateway port (MCP SSE, SDK WS, HTTP webhooks)
  admin_port: 8766        # Admin API port (separate for security)
  admin_token: "s3cret-t0ken-ch4nge-me"   # Protect admin API
  log_level: info

# ---- WeChat Bot accounts (downstream) -------------------------------------
accounts:
  team-bot:
    credentials: ~/.clawbot-gateway/accounts/team-bot.json

# ---- Upstream endpoints ----------------------------------------------------
endpoints:
  project-alpha:
    name: "Project Alpha"
    type: mcp               # For Claude Code users
    description: "Alpha team Claude Code endpoint"

  project-beta:
    name: "Project Beta"
    type: mcp               # Another MCP endpoint
    description: "Beta team Claude Code endpoint"

  support-bot:
    name: "Support Bot"
    type: sdk               # For a custom Python bot
    description: "Automated support responses"

  analytics-webhook:
    name: "Analytics"
    type: http              # Webhook to external service
    url: "https://your-service.example.com/wechat-webhook"
    api_key: "webhook-secret-key"
    description: "Forward messages to analytics pipeline"

# ---- Routing ---------------------------------------------------------------
routing:
  strategy: active-endpoint     # Users select their active endpoint
  mention_prefix: "@"           # @endpoint-name to send to specific endpoint
  gateway_commands:
    - "/"                       # Slash commands like /list, /use, /help

# ---- Authorization ---------------------------------------------------------
authorization:
  mode: invite-code             # Users need an invite code to join
  default_endpoints:
    - project-alpha             # Auto-bind new users to this endpoint
  admins:
    - "your-wechat-id@im.wechat"   # Your WeChat user ID (visible in logs)

# ---- Archive (optional) ----------------------------------------------------
archive:
  enabled: true
  path: ~/.clawbot-gateway/archive.db
  retention_days: 30            # Keep 30 days of message history
```

### Step 4: Start the Gateway

```bash
clawbot-gateway start
```

The gateway starts listening on port 8765 (main) and 8766 (admin API).

### Step 5: Each Developer Connects Their Client

**Developer using Claude Code (bridge mode):**

```bash
# Register MCP server pointing to the gateway
claude mcp add wechat -- wechat-clawbot-cc serve \
  --gateway http://your-server:8765 \
  --endpoint project-alpha \
  --api-key s3cret-t0ken-ch4nge-me

# Start Claude Code with WeChat channel
claude --dangerously-load-development-channels server:wechat
```

**Developer using Codex (bridge mode):**

```bash
codex mcp add wechat -- wechat-clawbot-cc serve \
  --gateway http://your-server:8765 \
  --endpoint project-beta \
  --api-key s3cret-t0ken-ch4nge-me
```

**Developer running a custom bot (SDK):**

```bash
pip install "wechat-clawbot[sdk]"
```

```python
import asyncio
from wechat_clawbot.sdk import ClawBotClient

async def main():
    async with ClawBotClient(
        gateway_url="http://your-server:8765",
        endpoint_id="support-bot",
    ) as client:
        async for msg in client.messages():
            print(f"From {msg.sender_id}: {msg.text}")
            await client.reply(msg.sender_id, f"Thanks for your message!")

asyncio.run(main())
```

### Step 6: Onboard Users

Since the gateway is set to `invite-code` mode, create invite codes and share them:

```bash
# Create an invite code for project-alpha, 10 uses, expires in 48 hours
clawbot-gateway invite create project-alpha --max-uses 10 --ttl 48 \
  --gateway http://your-server:8766 \
  --admin-token s3cret-t0ken-ch4nge-me
```

Share the code with team members. They send this in WeChat:

```
/bind <invite-code>
```

### Step 7: Day-to-Day Management

```bash
# Check gateway status
clawbot-gateway status --gateway http://your-server:8766 --admin-token s3cret-t0ken-ch4nge-me

# List all users
clawbot-gateway user list --gateway http://your-server:8766 --admin-token s3cret-t0ken-ch4nge-me

# View recent messages
clawbot-gateway logs -n 20 --gateway http://your-server:8766 --admin-token s3cret-t0ken-ch4nge-me
```

To avoid typing the gateway URL and token every time, use environment variables:

```bash
export CLAWBOT_GATEWAY_URL=http://your-server:8766
export CLAWBOT_ADMIN_TOKEN=s3cret-t0ken-ch4nge-me

# Now commands are shorter:
clawbot-gateway status
clawbot-gateway user list
clawbot-gateway logs -n 20
```

---

## Scenario 4: Invite Code Workflow

The invite system lets admins control who can use the bot without managing a static allowlist.

### How It Works

1. Admin creates an invite code tied to a specific endpoint
2. Admin shares the code with a team member (Slack, email, etc.)
3. Team member sends `/bind <code>` in their WeChat chat with the ClawBot
4. The gateway validates the code, binds the user to the endpoint, and confirms

### Create an Invite Code

```bash
# Basic: 1 use, no expiry
clawbot-gateway invite create project-alpha

# 5 uses, expires in 24 hours
clawbot-gateway invite create project-alpha --max-uses 5 --ttl 24

# Unlimited uses, expires in 72 hours
clawbot-gateway invite create project-alpha --max-uses 0 --ttl 72
```

### List Active Invite Codes

```bash
clawbot-gateway invite list
```

Output shows the code, endpoint, remaining uses, and expiry time.

### User Redeems the Code

In WeChat, the user sends:

```
/bind aB3dEf_g
```

The gateway responds:

```
Bound to endpoint: Project Alpha
```

### Authorization Modes Comparison

| Mode | Behavior |
|------|----------|
| `open` | Anyone can send messages, no invite needed |
| `allowlist` | Only users in the `admins` list or pre-registered users can interact |
| `invite-code` | Users must redeem an invite code to gain access; admins always have access |

### Configuration

In `gateway.yaml`:

```yaml
authorization:
  mode: invite-code
  default_endpoints:
    - project-alpha       # Users get auto-bound to these when they first interact
  admins:
    - "admin@im.wechat"  # Admins bypass invite-code requirement
```

---

## Scenario 5: Custom Bot Development (SDK)

You want to build a custom WeChat bot using Python. The SDK provides a simple WebSocket client that connects to the gateway.

### Install

```bash
pip install "wechat-clawbot[sdk]"
```

### Complete Working Example: Echo Bot

```python
import asyncio
from wechat_clawbot.sdk import ClawBotClient

async def main():
    async with ClawBotClient(
        gateway_url="http://localhost:8765",
        endpoint_id="echo-bot",
    ) as client:
        print("Echo bot connected, waiting for messages...")
        async for msg in client.messages():
            print(f"[{msg.sender_id}] {msg.text}")
            await client.reply(msg.sender_id, f"Echo: {msg.text}")

asyncio.run(main())
```

### ClawBotClient API

```python
ClawBotClient(
    gateway_url: str,       # Gateway HTTP URL (e.g., "http://localhost:8765")
    endpoint_id: str,       # Your endpoint ID in the gateway config
    token: str = "",        # Optional auth token
    reconnect: bool = True, # Auto-reconnect on disconnect
    reconnect_delay: float = 5.0,  # Seconds between reconnect attempts
)
```

**Methods:**

| Method | Description |
|--------|-------------|
| `await client.connect()` | Connect to the gateway WebSocket |
| `await client.close()` | Close the connection |
| `async for msg in client.messages()` | Iterate over incoming messages |
| `await client.reply(sender_id, text)` | Send a reply to a user |
| `await client.ping()` | Send a keepalive ping |

**Message object:**

| Field | Type | Description |
|-------|------|-------------|
| `sender_id` | `str` | WeChat user ID (e.g., `user@im.wechat`) |
| `text` | `str` | Message text content |
| `context_token` | `str | None` | Context token for session tracking |

### Handling Different Message Types

The SDK currently delivers text messages. Media messages are converted to text descriptions by the gateway. To handle messages differently based on content:

```python
async for msg in client.messages():
    if msg.text.startswith("/"):
        # Handle bot-specific commands
        command = msg.text.split()[0][1:]
        await handle_command(client, msg, command)
    elif "help" in msg.text.lower():
        await client.reply(msg.sender_id, "Available commands: /info, /stats")
    else:
        await client.reply(msg.sender_id, f"Echo: {msg.text}")
```

### Auto-Reconnect Behavior

The client automatically reconnects if the WebSocket connection drops. You can disable this:

```python
client = ClawBotClient(
    gateway_url="http://localhost:8765",
    endpoint_id="my-bot",
    reconnect=False,  # Raise exception on disconnect instead
)
```

### Gateway Configuration for SDK Endpoint

In your `gateway.yaml`, define the endpoint as type `sdk`:

```yaml
endpoints:
  echo-bot:
    name: "Echo Bot"
    type: sdk
    description: "Simple echo bot for testing"
```

---

## Scenario 6: Third-party Webhook Integration

You want to connect an external service (Dify, n8n, Zapier, or any HTTP-capable system) to receive WeChat messages and send replies.

### How It Works

1. **Inbound:** The gateway POSTs each message to your service's webhook URL as JSON
2. **Synchronous reply:** Your service can include a reply in the HTTP response body
3. **Asynchronous reply:** Your service can POST a reply later to the gateway's callback URL

### Step 1: Configure the HTTP Endpoint

In `gateway.yaml`:

```yaml
endpoints:
  my-webhook:
    name: "Webhook Service"
    type: http
    url: "https://your-service.example.com/wechat/inbound"
    api_key: "your-webhook-secret"
```

### Step 2: Receive Messages

The gateway POSTs to your URL with this payload:

```json
{
  "sender_id": "user123@im.wechat",
  "text": "Hello, I need help with my order",
  "context_token": "tok_abc123..."
}
```

Headers:
- `Content-Type: application/json`
- `Authorization: Bearer your-webhook-secret` (if `api_key` is configured)

### Step 3: Reply (Synchronous)

Return a JSON response with a `reply` or `text` field:

```json
{
  "reply": "Thanks for contacting us! Your order is being processed."
}
```

The gateway will automatically forward this reply to the WeChat user.

### Step 4: Reply (Asynchronous via Callback)

If your service needs more time to process, return a 200 OK without a reply, then POST to the callback URL later:

```
POST http://your-gateway:8765/http/my-webhook/callback
Content-Type: application/json
Authorization: Bearer your-webhook-secret

{
  "sender_id": "user123@im.wechat",
  "text": "Your order #12345 has been shipped!"
}
```

### Authentication

The `api_key` in the endpoint configuration serves two purposes:
- **Outbound:** Added as `Authorization: Bearer <api_key>` when the gateway POSTs to your URL
- **Inbound (callback):** Verified when your service POSTs to the `/http/{id}/callback` endpoint

### Example: n8n Integration

1. In n8n, create a Webhook trigger node
2. Set the webhook URL as the endpoint URL in gateway.yaml
3. Process the message in your n8n workflow
4. Use an HTTP Request node to POST the reply to the callback URL

### Example: Simple Flask Webhook

```python
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/wechat/inbound", methods=["POST"])
def handle_message():
    data = request.json
    sender = data["sender_id"]
    text = data["text"]

    # Process the message
    reply_text = generate_response(text)

    return jsonify({"reply": reply_text})

def generate_response(text):
    return f"Received: {text}"

if __name__ == "__main__":
    app.run(port=5000)
```

---

## Scenario 7: Remote Gateway Administration

You have a gateway running on a remote server and want to manage it from your local machine.

### Option 1: Using the --gateway Flag

Every CLI command accepts `--gateway` and `--admin-token` flags:

```bash
clawbot-gateway status \
  --gateway http://my-server:8766 \
  --admin-token s3cret-t0ken

clawbot-gateway user list \
  --gateway http://my-server:8766 \
  --admin-token s3cret-t0ken
```

### Option 2: Using Environment Variables

Set these once and all commands use them automatically:

```bash
export CLAWBOT_GATEWAY_URL=http://my-server:8766
export CLAWBOT_ADMIN_TOKEN=s3cret-t0ken

# Now just use commands directly:
clawbot-gateway status
clawbot-gateway user list
clawbot-gateway endpoint list
clawbot-gateway logs -n 50
```

### Common Admin Operations

**Check if the gateway is running:**

```bash
clawbot-gateway status
```

Output:

```json
{
  "status": "running",
  "accounts": 1,
  "endpoints": { "total": 3, "online": 2 },
  "users": 12
}
```

**List all endpoints and their status:**

```bash
clawbot-gateway endpoint list
```

**View information about a specific user:**

```bash
clawbot-gateway user info "user123@im.wechat"
```

**Bind a user to an endpoint (administrative override):**

```bash
clawbot-gateway user bind "user123@im.wechat" project-alpha
```

**Unbind a user from an endpoint:**

```bash
clawbot-gateway user unbind "user123@im.wechat" project-alpha
```

**Add a new endpoint at runtime (no restart needed):**

```bash
clawbot-gateway endpoint add new-endpoint \
  --name "New Endpoint" \
  --type mcp
```

**Remove an endpoint:**

```bash
clawbot-gateway endpoint remove old-endpoint
```

**View recent message logs:**

```bash
# Last 50 messages (default)
clawbot-gateway logs

# Last 100 messages for a specific endpoint
clawbot-gateway logs -n 100 --endpoint project-alpha

# Messages from a specific user
clawbot-gateway logs --user "user123@im.wechat"
```

### JSON Output

Add `--json` to any command for machine-readable output, useful for scripting:

```bash
clawbot-gateway status --json | jq '.endpoints.online'
```

---

## Scenario 8: Monitoring and Maintenance

Day-to-day operations for keeping a gateway running smoothly.

### Checking Gateway Status

```bash
clawbot-gateway status
```

This shows:
- Whether the gateway process is running
- Number of connected accounts
- Number of endpoints (total and online)
- Number of known users

### Viewing Message Logs

If archiving is enabled (`archive.enabled: true` in gateway.yaml):

```bash
# Recent messages
clawbot-gateway logs -n 20

# Filter by endpoint
clawbot-gateway logs --endpoint project-alpha -n 50

# Filter by user
clawbot-gateway logs --user "user123@im.wechat" -n 50

# JSON output for processing
clawbot-gateway logs --json | jq '.messages[] | select(.direction == "inbound")'
```

### Monitoring Endpoint Health

Endpoints can be in three states:
- **online** — A client is connected and active
- **offline** — No client connected
- **error** — Connection established but encountering errors

```bash
# Quick overview
clawbot-gateway endpoint list

# Detailed status (via admin API)
clawbot-gateway status --json | jq '.endpoints'
```

### Handling Session Expiry

WeChat bot sessions expire periodically. When this happens:
- The gateway detects the expiry and pauses polling for that account
- Messages stop being received on the expired account
- After the pause period (default 60 seconds), the gateway will retry

To fix a permanently expired session:

```bash
# Re-login the bot account
clawbot-gateway account add
```

Then restart the gateway:

```bash
clawbot-gateway stop
clawbot-gateway start
```

### Graceful Shutdown

The gateway handles SIGINT and SIGTERM for graceful shutdown:

```bash
# Stop via PID file
clawbot-gateway stop

# Or send signal directly
kill -SIGINT $(cat ~/.clawbot-gateway/gateway.pid)
```

### Log Files

The gateway writes application logs to stderr (standard for server processes). For persistent logging, redirect output:

```bash
clawbot-gateway start 2>&1 | tee -a /var/log/clawbot-gateway.log
```

The WeChat client also writes JSON-line logs to `/tmp/openclaw/openclaw-YYYY-MM-DD.log`.

### Cleaning Up Expired Data

Invite codes are automatically purged when expired or exhausted. Message archive retention is controlled by `retention_days` in the config:

```yaml
archive:
  enabled: true
  retention_days: 30    # Automatically delete messages older than 30 days
                        # 0 = keep forever
```

---

## Scenario 9: Developing and Extending the Gateway

For developers who want to contribute to or customize wechat-clawbot.

### Project Structure Overview

```
src/wechat_clawbot/
  api/                  # ilink HTTP API client and protocol types
  auth/                 # QR login, account storage, credential management
  cdn/                  # AES-128-ECB CDN upload/download pipeline
  claude_channel/       # Claude Code MCP Channel bridge
    cli.py              #   CLI (wechat-clawbot-cc)
    bridge.py           #   Bridge mode (gateway SSE -> MCP stdio)
    server.py           #   Direct mode (WeChat poll -> MCP stdio)
    credentials.py      #   Credential storage (~/.claude/channels/wechat/)
    setup.py            #   Interactive QR login
  config/               # Pydantic configuration schema
  gateway/              # Multi-Bot, multi-endpoint routing gateway
    channels/           #   Sub-channel implementations
      base.py           #     SubChannel protocol + callback types
      mcp_channel.py    #     MCP SSE sub-channel
      sdk_channel.py    #     WebSocket SDK sub-channel
      http_channel.py   #     HTTP webhook sub-channel
    admin.py            #   Admin HTTP API (Starlette)
    app.py              #   Main gateway orchestrator (GatewayApp)
    cli.py              #   CLI entry point (clawbot-gateway)
    config.py           #   gateway.yaml schema and loader
    commands.py         #   WeChat in-chat command handlers
    delivery.py         #   SQLite-backed delivery queue
    router.py           #   Message routing engine
    session.py          #   User session/state persistence
    endpoint_manager.py #   Endpoint registry + health tracking
    invite.py           #   Invite code system
    auth.py             #   Authorization module
    archive.py          #   Message archive (SQLite)
    db.py               #   AsyncSQLiteStore base class
    types.py            #   Core dataclasses and enums
  media/                # Media download, MIME types, SILK transcoding
  messaging/            # Inbound conversion, send pipeline, slash commands
    mcp_defs.py         #   Shared MCP tool definitions
  monitor/              # Long-poll monitor loop
  sdk/                  # ClawBotClient library for custom bots
  storage/              # State directory, sync buffer persistence
  util/                 # Logger, ID generation, sensitive field redaction
```

### Key Conventions

- **Async/await with anyio** — All I/O uses anyio for structured concurrency (not raw asyncio)
- **Pydantic for configuration** — Config models use Pydantic v2 with validation
- **Dataclasses for runtime types** — `types.py` uses `@dataclass` for runtime data structures
- **SQLite with WAL mode** — Delivery queue and archive use WAL-mode SQLite via `AsyncSQLiteStore`
- **Thread offloading** — SQLite operations run in worker threads via `anyio.to_thread.run_sync`
- **Starlette for HTTP** — Gateway and admin API use Starlette ASGI
- **No markdown in WeChat replies** — Gateway command responses use plain text (WeChat does not render markdown)
- **Ruff for linting** — Configured in `pyproject.toml`, targeting Python 3.10+

### Adding a New Sub-Channel Type

1. Create `src/wechat_clawbot/gateway/channels/my_channel.py`
2. Implement the `SubChannel` protocol from `base.py`:

```python
from .base import ReplyCallback

class MyChannel:
    def __init__(self, on_reply: ReplyCallback) -> None:
        self._on_reply = on_reply

    async def start(self) -> None:
        """Initialize your channel (open connections, etc.)."""
        ...

    async def stop(self) -> None:
        """Clean up resources."""
        ...

    async def deliver_message(
        self,
        endpoint_id: str,
        sender_id: str,
        text: str,
        context_token: str | None = None,
        media_path: str = "",
        media_type: str = "",
    ) -> bool:
        """Deliver a message to the endpoint. Return True on success."""
        ...

    async def send_reply(
        self,
        endpoint_id: str,
        sender_id: str,
        text: str,
        context_token: str | None = None,
    ) -> None:
        """Send a reply back through this channel."""
        ...

    def is_endpoint_connected(self, endpoint_id: str) -> bool:
        ...

    def get_connected_endpoints(self) -> list[str]:
        ...
```

3. Register the new channel type in `ChannelType` enum (`types.py`)
4. Wire it into `GatewayApp.start()` in `app.py`

### Adding a New Gateway Command

1. Open `src/wechat_clawbot/gateway/commands.py`
2. Add a handler function:

```python
async def _handle_mycommand(ctx: GatewayCommandContext) -> str:
    """Handle /mycommand."""
    return "This is my custom command!"
```

3. Register it in the `HANDLERS` dict at the bottom of the file:

```python
HANDLERS.update({
    # ... existing handlers ...
    "mycommand": _handle_mycommand,
})
```

4. If necessary, update `GATEWAY_COMMANDS` frozenset

### Running the Test Suite

```bash
# Clone and set up
git clone https://github.com/nightsailer/wechat-clawbot.git
cd wechat-clawbot
uv sync

# Run all tests
uv run pytest tests/ -v

# Run a specific test file
uv run pytest tests/test_gateway.py -v

# Run with coverage
uv run pytest tests/ --cov=wechat_clawbot

# Lint
uv run ruff check src/ tests/

# Format
uv run ruff format src/ tests/

# Full pre-commit check
uv run ruff check src/ tests/ && uv run ruff format src/ tests/
```

### Code Style

- Imports: standard library, third-party, local — separated by blank lines
- Type hints: required for all public functions
- Docstrings: required for all public classes and functions
- Line length: configured in `pyproject.toml` (via Ruff)
- Use `from __future__ import annotations` in all modules

---

## Appendix A: Complete CLI Reference with Examples

### Global Flags

All `clawbot-gateway` commands accept these flags:

| Flag | Description |
|------|-------------|
| `--config <path>` | Path to `gateway.yaml` (default: `~/.clawbot-gateway/gateway.yaml`) |
| `--json` | Output in JSON format |
| `--yes`, `-y` | Skip confirmation prompts |
| `--gateway <url>` | Remote gateway admin URL (or set `CLAWBOT_GATEWAY_URL`) |
| `--admin-token <token>` | Bearer token for admin API (or set `CLAWBOT_ADMIN_TOKEN`) |

### init — Initialize Configuration

```bash
# Create default gateway.yaml
clawbot-gateway init
```

Creates `~/.clawbot-gateway/gateway.yaml` if it does not exist. Shows next steps on success.

### start — Start the Gateway

```bash
# Start with default config
clawbot-gateway start

# Start with custom config path
clawbot-gateway start --config /etc/clawbot/gateway.yaml
```

Writes a PID file to `~/.clawbot-gateway/gateway.pid`. Handles SIGINT/SIGTERM for graceful shutdown.

### stop — Stop the Gateway

```bash
clawbot-gateway stop
```

Reads the PID file and sends SIGINT to the gateway process.

### status — Show Gateway Status

```bash
# Local status (reads config + PID file)
clawbot-gateway status

# Remote status (queries admin API)
clawbot-gateway status --gateway http://server:8766
```

### Account Management

```bash
# Add a new bot account (interactive QR login)
clawbot-gateway account add

# List all configured accounts
clawbot-gateway account list

# List accounts from a remote gateway
clawbot-gateway account list --gateway http://server:8766

# Show account status (requires running gateway)
clawbot-gateway account status
clawbot-gateway account status main-bot

# Remove an account (manual edit required)
clawbot-gateway account remove old-bot
```

### Endpoint Management

```bash
# List all endpoints (local)
clawbot-gateway endpoint list

# List endpoints (remote)
clawbot-gateway endpoint list --gateway http://server:8766

# Add an MCP endpoint
clawbot-gateway endpoint add claude-dev --name "Claude Dev" --type mcp \
  --gateway http://server:8766

# Add an SDK endpoint
clawbot-gateway endpoint add custom-bot --name "Custom Bot" --type sdk \
  --gateway http://server:8766

# Add an HTTP webhook endpoint
clawbot-gateway endpoint add webhook --name "Webhook" --type http \
  --url https://example.com/hook \
  --gateway http://server:8766

# Remove an endpoint
clawbot-gateway endpoint remove old-endpoint --gateway http://server:8766
```

### User Management

```bash
# List all known users
clawbot-gateway user list

# Show info for a specific user
clawbot-gateway user info "user123@im.wechat"

# Bind a user to an endpoint (admin action)
clawbot-gateway user bind "user123@im.wechat" project-alpha

# Unbind a user from an endpoint
clawbot-gateway user unbind "user123@im.wechat" project-alpha

# Allow a user (adds to allowlist — edit gateway.yaml)
clawbot-gateway user allow "user123@im.wechat"

# Block a user (removes access — edit gateway.yaml)
clawbot-gateway user block "user123@im.wechat"
```

**Scenario: New user joins the team**

```bash
# 1. Create an invite code
clawbot-gateway invite create project-alpha --max-uses 1 --ttl 24

# 2. Share the code with the new team member
# 3. They send in WeChat: /bind <code>

# 4. Verify they're connected
clawbot-gateway user list --json | jq '.users[] | select(.user_id | contains("new-user"))'
```

**Scenario: User leaves the team**

```bash
# Unbind from all endpoints
clawbot-gateway user unbind "user@im.wechat" project-alpha
clawbot-gateway user unbind "user@im.wechat" project-beta
```

**Scenario: Switch user to a different endpoint**

```bash
# Unbind old, bind new
clawbot-gateway user unbind "user@im.wechat" project-alpha
clawbot-gateway user bind "user@im.wechat" project-beta
```

### Invite Code Management

```bash
# List all active invite codes
clawbot-gateway invite list

# Create a single-use invite code (default)
clawbot-gateway invite create project-alpha

# Create a multi-use invite code with expiry
clawbot-gateway invite create project-alpha --max-uses 10 --ttl 48

# Create an unlimited invite code (no max uses, no expiry)
clawbot-gateway invite create project-alpha --max-uses 0 --ttl 0
```

**Scenario: Onboard 5 team members to project-x**

```bash
# Create a 5-use invite code that expires in 24 hours
clawbot-gateway invite create project-x --max-uses 5 --ttl 24

# Output: {"code": "aB3dEf_g", "endpoint_id": "project-x"}

# Share the code: "Send /bind aB3dEf_g in WeChat to join project-x"

# Monitor usage
clawbot-gateway invite list --json | jq '.invites[] | select(.endpoint_id == "project-x")'
```

### Log Viewing

```bash
# View last 50 messages (default)
clawbot-gateway logs

# View last 100 messages
clawbot-gateway logs -n 100

# Filter by endpoint
clawbot-gateway logs --endpoint project-alpha

# Filter by user
clawbot-gateway logs --user "user123@im.wechat"

# Combine filters
clawbot-gateway logs --endpoint project-alpha --user "user123@im.wechat" -n 20

# JSON output for scripting
clawbot-gateway logs --json -n 10
```

---

## Appendix B: Configuration Reference

Complete reference for every field in `gateway.yaml`.

### `gateway` Section

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `host` | string | `"0.0.0.0"` | IP address to bind to. Use `0.0.0.0` for all interfaces, `127.0.0.1` for localhost only. |
| `port` | int | `8765` | Main gateway port. Serves MCP SSE (`/mcp/{id}/sse`), SDK WebSocket (`/sdk/{id}/ws`), and HTTP callbacks (`/http/{id}/callback`). |
| `admin_port` | int | `8766` | Admin API port. Serves `/api/*` endpoints. Use a separate port so you can firewall admin access. |
| `admin_token` | string | `""` | Bearer token for admin API authentication. When empty, the admin API has no auth (not recommended for production). |
| `log_level` | string | `"info"` | Log verbosity. Options: `debug`, `info`, `warning`, `error`. |

### `accounts` Section

A dictionary of WeChat Bot accounts. Key is the account ID (your chosen name).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `credentials` | string or null | `null` | Path to a JSON credentials file (created by `clawbot-gateway account add`). Supports `~` expansion. |
| `token` | string or null | `null` | Inline bot token (alternative to credentials file). |
| `base_url` | string | `"https://ilinkai.weixin.qq.com"` | iLink API base URL. Change only if you need a custom server. |

You must provide either `credentials` or `token` for each account. The credentials file is the recommended approach.

### `endpoints` Section

A dictionary of upstream endpoints. Key is the endpoint ID.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | `""` | Human-readable name shown in `/list` command output. Defaults to the endpoint ID if empty. |
| `type` | string | `"mcp"` | Channel type: `mcp`, `sdk`, or `http`. |
| `url` | string | `""` | For `http` type: webhook URL to POST messages to. For `mcp`/`sdk`: not used (clients connect to the gateway). |
| `tags` | list[string] | `[]` | Arbitrary tags for organizing endpoints. |
| `api_key` | string | `""` | For `http` type: Bearer token for webhook authentication. For `mcp`/`sdk`: not used. |
| `description` | string | `""` | Description for documentation purposes. |

### `routing` Section

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `strategy` | string | `"active-endpoint"` | Routing strategy. `active-endpoint`: route to user's selected endpoint. `prefix`: route by @mention prefix. `smart`: auto-detect. |
| `mention_prefix` | string | `"@"` | Prefix for mentioning endpoints by name (e.g., `@claude Hello`). |
| `gateway_commands` | list[string] | `["/"]` | Prefix(es) that trigger gateway commands like `/list`, `/use`, `/help`. |

### `authorization` Section

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `mode` | string | `"allowlist"` | Authorization mode: `open`, `allowlist`, or `invite-code`. |
| `default_endpoints` | list[string] | `[]` | Endpoint IDs auto-bound to new users. |
| `admins` | list[string] | `[]` | WeChat user IDs with admin privileges. Admins bypass authorization and can use `/admin` command. |

### `archive` Section

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `false` | Enable message archiving. When enabled, all messages are stored in SQLite. |
| `storage` | string | `"sqlite"` | Storage backend. Only `sqlite` is currently supported. |
| `path` | string | `""` | Path to the archive database file. Defaults to `~/.clawbot-gateway/archive.db` when empty. Supports `~` expansion. |
| `retention_days` | int | `0` | Number of days to retain archived messages. `0` = keep forever. |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `CLAWBOT_GATEWAY_URL` | Default gateway admin URL (alternative to `--gateway` flag) |
| `CLAWBOT_ADMIN_TOKEN` | Default admin Bearer token (alternative to `--admin-token` flag) |
| `CLAWBOT_GATEWAY_CONFIG` | Path to `gateway.yaml` (alternative to `--config` flag) |

---

## Appendix C: Troubleshooting

### QR Code Expired

**Symptom:** The QR code times out during login.

**Solution:**

```bash
# For Channel Mode:
wechat-clawbot-cc setup

# For Gateway Mode:
clawbot-gateway account add
```

QR codes are valid for approximately 8 minutes. Scan promptly.

### "Endpoint Not Connected"

**Symptom:** Users send messages but get no response; `/status` shows the endpoint as offline.

**Solution:** The AI client (Claude Code, Codex, or SDK bot) is not running or cannot reach the gateway.

1. Verify the client is running and connected
2. Check the gateway URL is correct and reachable
3. For bridge mode, check that `--gateway` and `--endpoint` flags are correct
4. Check firewall rules — the gateway port must be accessible

### "Unauthorized" Errors

**Symptom:** CLI commands return `{"error": "unauthorized"}`.

**Solution:**

```bash
# Make sure admin_token in gateway.yaml matches your --admin-token flag
clawbot-gateway status --admin-token "correct-token"

# Or set the environment variable
export CLAWBOT_ADMIN_TOKEN="correct-token"
```

### Missing Dependencies

**Symptom:** `ModuleNotFoundError` on startup.

**Solution:**

```bash
# For gateway mode
pip install "wechat-clawbot[gateway]"

# For SDK client
pip install "wechat-clawbot[sdk]"

# For voice transcoding
pip install "wechat-clawbot[silk]"

# All extras
pip install "wechat-clawbot[gateway,sdk,silk]"
```

### Bridge Mode "SSE Connection Failed"

**Symptom:** Bridge logs show `SSE connection failed: 401` or `SSE connection error`.

**Solution:**

1. Verify the gateway URL and port:
   ```bash
   curl http://your-server:8765/mcp/your-endpoint/sse
   ```
2. If you get a 401, the `--api-key` does not match the gateway's `admin_token`
3. If connection refused, check that the gateway is running and the port is correct
4. The bridge uses exponential backoff and will auto-retry

### Messages Not Being Delivered

**Symptom:** Messages arrive at the gateway but are not forwarded to the endpoint.

**Possible causes:**

1. **User not bound to endpoint:** The user needs to `/bind <endpoint>` first
2. **Wrong active endpoint:** The user's active endpoint is different; use `/use <name>` to switch
3. **Endpoint offline:** The AI client is not connected; check with `/status`
4. **Authorization denied:** In `allowlist` mode, the user may not be authorized

### WeChat Session Expired

**Symptom:** Gateway stops receiving messages; logs show `session expired` or error code `-14`.

**Solution:** The WeChat bot session has expired. This happens periodically.

```bash
# Re-authenticate
clawbot-gateway account add

# Restart the gateway
clawbot-gateway stop
clawbot-gateway start
```

### Gateway Won't Start

**Symptom:** `clawbot-gateway start` exits immediately with an error.

**Common causes:**

1. **Invalid YAML:** Check your `gateway.yaml` for syntax errors
2. **No accounts defined:** At least one account is required
3. **No endpoints defined:** At least one endpoint is required
4. **Port in use:** Another process is using port 8765 or 8766

```bash
# Validate the config
python -c "from wechat_clawbot.gateway.config import load_gateway_config; load_gateway_config()"

# Check port availability
lsof -i :8765
lsof -i :8766
```
