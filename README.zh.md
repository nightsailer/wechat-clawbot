# wechat-clawbot

微信 ClawBot ilink API 的 Python SDK，内置 Claude Code Channel 桥接器。

移植自 [@tencent-weixin/openclaw-weixin](https://www.npmjs.com/package/@tencent-weixin/openclaw-weixin)（TypeScript 版）。

```
微信 (iOS) --> ClawBot --> ilink API --> [wechat-clawbot] --> Claude Code 会话
                                                |
Claude Code  <-- MCP Channel 协议  <--  wechat_reply / wechat_send_file / wechat_typing
```

## 功能特性

- **完整 ilink API 客户端** — getUpdates 长轮询、sendMessage、getConfig、sendTyping
- **多账户支持** — 二维码扫码登录、凭证存储、账户索引
- **媒体处理管道** — AES-128-ECB 加密 CDN 上传/下载，支持图片/视频/文件/语音
- **SILK 转码** — 语音消息转 WAV（可选依赖）
- **消息处理** — 入站消息转换、斜杠命令、调试模式、错误通知
- **Claude Code Channel** — MCP 服务器，将微信消息桥接到 Claude Code 会话
- **异步优先** — 基于 httpx + anyio，使用共享连接池

## 环境要求

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)（推荐）或 pip

## 安装

```bash
uv add wechat-clawbot
```

或使用 pip：

```bash
pip install wechat-clawbot
```

可选扩展：

```bash
uv add "wechat-clawbot[silk]"    # SILK 语音转码
uv add "wechat-clawbot[socks]"   # SOCKS 代理支持（如使用 SOCKS5 代理）
```

## 快速开始 — Claude Code Channel

### 1. 微信扫码登录

```bash
wechat-clawbot-cc setup
```

用微信扫描终端中的二维码。凭据保存到 `~/.claude/channels/wechat/account.json`。

### 2. 注册 MCP 服务器

```bash
claude mcp add wechat -- wechat-clawbot-cc serve
```

### 3. 启动 Claude Code + 微信通道

```bash
claude --channels server:wechat
```

在微信 ClawBot 中发送消息，Claude 会自动回复。

## 快速开始 — Python SDK

```python
import asyncio
from wechat_clawbot.api.client import WeixinApiOptions, get_updates, send_message
from wechat_clawbot.api.types import (
    MessageType, MessageState, MessageItemType,
    SendMessageReq, WeixinMessage, MessageItem, TextItem,
)

async def main():
    opts = WeixinApiOptions(base_url="https://ilinkai.weixin.qq.com", token="your-bot-token")

    # 长轮询获取消息
    resp = await get_updates(base_url=opts.base_url, token=opts.token)
    for msg in resp.msgs or []:
        print(f"发送者: {msg.from_user_id}, 内容: {msg.item_list}")

    # 发送回复
    await send_message(opts, SendMessageReq(msg=WeixinMessage(
        to_user_id="user@im.wechat",
        client_id="my-client-id",
        message_type=MessageType.BOT,
        message_state=MessageState.FINISH,
        item_list=[MessageItem(type=MessageItemType.TEXT, text_item=TextItem(text="你好！"))],
        context_token="来自getupdates的token",
    )))

asyncio.run(main())
```

## 项目结构

```
src/wechat_clawbot/
  api/              # ilink HTTP API 客户端和协议类型
  auth/             # QR 登录、账户存储、授权配对
  cdn/              # AES-128-ECB 加密、CDN 上传/下载
  config/           # Pydantic 配置 Schema
  media/            # 媒体下载、MIME 类型、SILK 转码
  messaging/        # 入站转换、发送、斜杠命令、处理管道
  monitor/          # 长轮询监控循环
  storage/          # 状态目录、同步缓冲区持久化
  util/             # 日志、ID 生成、脱敏
  claude_channel/   # Claude Code MCP Channel 桥接（CLI + 服务器）
```

## 开发

```bash
git clone https://github.com/nightsailer/wechat-clawbot.git
cd wechat-clawbot
uv sync

# 运行测试
uv run pytest tests/ -v

# 代码检查
uv run ruff check src/ tests/

# 代码格式化
uv run ruff format src/ tests/
```

## 文档

- [iLink Bot 协议](docs/ilink-protocol.md) — 微信 ClawBot iLink API 协议参考
- [Python SDK API](docs/api.md) — wechat-clawbot 公共 API 参考

## 协议

MIT
