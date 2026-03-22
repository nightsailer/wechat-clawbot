# wechat-clawbot

Python SDK for the WeChat ClawBot ilink API, with a built-in Claude Code Channel bridge.

Ported from [@tencent-weixin/openclaw-weixin](https://www.npmjs.com/package/@tencent-weixin/openclaw-weixin) (TypeScript).

```
WeChat (iOS) --> ClawBot --> ilink API --> [wechat-clawbot] --> Claude Code Session
                                                  |
Claude Code  <-- MCP Channel Protocol  <--  wechat_reply / wechat_send_file / wechat_typing
```

## Features

- **Full ilink API client** — getUpdates long-poll, sendMessage, getConfig, sendTyping
- **Multi-account support** — QR code login, credential storage, account index
- **Media pipeline** — AES-128-ECB encrypted CDN upload/download, image/video/file/voice
- **SILK transcoding** — voice message to WAV conversion (optional)
- **Message processing** — inbound conversion, slash commands, debug mode, error notices
- **Claude Code Channel** — MCP server bridging WeChat messages into Claude Code sessions
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
uv add "wechat-clawbot[silk]"    # SILK voice transcoding
uv add "wechat-clawbot[socks]"   # SOCKS proxy support (e.g. behind a SOCKS5 proxy)
```

## Quick Start — Claude Code Channel

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
claude --channels server:wechat
```

Send a message in WeChat ClawBot, and Claude will reply.

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

- [iLink Bot Protocol](docs/ilink-protocol.md) — WeChat ClawBot iLink API protocol reference
- [Python SDK API](docs/api.md) — Public API reference for wechat-clawbot

## License

MIT
