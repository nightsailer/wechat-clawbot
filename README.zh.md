# wechat-clawbot

微信 iLink Bot SDK，内置多用户网关，支持 AI 后端接入（Claude Code、Codex、自定义机器人）。

移植自 [@tencent-weixin/openclaw-weixin](https://www.npmjs.com/package/@tencent-weixin/openclaw-weixin)（TypeScript 版），已同步上游 v2.1.1。

两种运行模式：

- **单通道模式（Channel Mode）** — 单用户、单端点 MCP 桥接，用于 Claude Code
- **网关模式（Gateway Mode）** (v0.4.0+) — M:N 多用户、多端点路由网关

```
                          ┌──────────────────────────────────────────────┐
单通道模式:                │  微信 ──> ilink API ──> [桥接] ──> Claude Code  │
                          └──────────────────────────────────────────────┘

                          ┌──────────────────────────────────────────────┐
                          │           ┌──> MCP SSE ──> Claude Code       │
网关模式:                  │  微信 ──┤──> SDK WS  ──> 自定义机器人         │
                          │   (M:N)   └──> HTTP    ──> Webhook 服务      │
                          └──────────────────────────────────────────────┘
```

## 功能特性

- **完整 ilink API 客户端** — getUpdates 长轮询、sendMessage、getConfig、sendTyping，支持 `iLink-App-Id` / `iLink-App-ClientVersion` 协议头
- **多账户支持** — 二维码扫码登录（支持 IDC 重定向）、凭证存储、过期账户自动清理
- **媒体处理管道** — AES-128-ECB 加密 CDN 上传/下载，支持 `full_url` 直传 URL，图片/视频/文件/语音
- **Context Token 持久化** — 进程重启不丢失会话上下文，磁盘备份 + 变更检测
- **SILK 转码** — 语音消息转 WAV（可选依赖）
- **消息处理** — 入站消息转换、斜杠命令、调试模式、错误通知
- **Claude Code Channel** — MCP 服务器，将微信消息桥接到 Claude Code 会话
- **网关模式** — M:N 路由网关，支持投递队列、会话管理、Admin API、SDK 客户端库
- **安全日志** — 自动脱敏 token、authorization 等敏感字段
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
uv add "wechat-clawbot[gateway]"  # 网关模式（+pyyaml, uvicorn）
uv add "wechat-clawbot[sdk]"      # SDK 客户端（+websockets）
uv add "wechat-clawbot[silk]"     # SILK 语音转码
uv add "wechat-clawbot[socks]"    # SOCKS 代理支持
```

| 扩展包 | 包含依赖 | 用途 |
|--------|----------|------|
| 核心（无扩展） | anyio, httpx, pydantic, cryptography, qrcode, mcp | 单通道模式（Claude Code Channel） |
| `[gateway]` | +pyyaml, uvicorn | 网关模式（clawbot-gateway 命令） |
| `[sdk]` | +websockets | SDK 客户端（ClawBotClient） |
| `[silk]` | +graiax-silkcoder | SILK 语音转码 |
| `[socks]` | +httpx[socks] | SOCKS 代理支持 |

## 单通道模式（Channel Mode）

### 快速开始 — Claude Code Channel

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

### 桥接模式（通过网关）

如果你已经运行了网关（Gateway），可以使用桥接模式，无需直接扫码登录。桥接模式连接到网关的 SSE 端点并转发消息：

```bash
# 以桥接模式注册 MCP 服务器
claude mcp add wechat -- wechat-clawbot-cc serve --gateway http://localhost:8765 --endpoint claude

# 启动 Claude Code + 微信通道
claude --channels server:wechat
```

桥接模式同时支持 Codex（通过 `wechat_get_messages` 工具和 `notifications/resources/updated` 通知）。

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

## 网关模式 (v0.4.0+)

网关提供 M:N 路由能力：多个微信 Bot 账户可以将消息路由到多个上游 AI 端点。每个用户可以通过聊天命令独立选择、切换和绑定端点。

### 架构概览

- **账户**（下游）— 一个或多个微信 Bot 账户，各自轮询 ilink API
- **端点**（上游）— 通过 MCP SSE、SDK WebSocket 或 HTTP Webhook 连接的 AI 后端
- **路由器** — 根据活跃端点、`@提及` 前缀或 `/命令` 将入站消息解析到对应端点
- **会话存储** — 每用户状态（活跃端点、绑定关系、上下文 Token）持久化到磁盘
- **投递队列** — 基于 SQLite 的持久化队列，支持重试逻辑
- **Admin API** — 独立的 HTTP 管理服务器，支持 Bearer Token 认证

### 快速开始

```bash
# 1. 初始化配置
clawbot-gateway init

# 2. 添加微信 Bot 账户（扫码登录）
clawbot-gateway account add

# 3. 编辑 ~/.clawbot-gateway/gateway.yaml 配置端点

# 4. 启动网关
clawbot-gateway start
```

### 配置示例

```yaml
# ~/.clawbot-gateway/gateway.yaml
gateway:
  host: 0.0.0.0
  port: 8765
  admin_port: 8766
  admin_token: "your-secret-token"

accounts:
  main-bot:
    credentials: ~/.clawbot-gateway/accounts/main-bot.json

endpoints:
  claude:
    name: "Claude Code"
    type: mcp
    url: "http://localhost:8080/sse"
  my-bot:
    name: "我的机器人"
    type: sdk

routing:
  strategy: active-endpoint
  mention_prefix: "@"

authorization:
  mode: allowlist
  admins: ["admin-user-id@im.wechat"]
```

### 微信命令

用户通过聊天命令与网关交互：

| 命令 | 说明 |
|------|------|
| `/list` | 列出可用端点 |
| `/use <名称>` | 切换活跃端点 |
| `/to <名称> <消息>` | 向指定端点发送单次消息 |
| `/status` | 显示当前会话状态 |
| `/bind` | 绑定到端点 |
| `/unbind` | 解绑端点 |
| `/help` | 显示帮助信息 |

### 子通道类型

| 类型 | 传输方式 | 适用场景 |
|------|----------|----------|
| `mcp` | SSE + JSON-RPC | Claude Code / MCP 兼容客户端 |
| `sdk` | WebSocket | 使用 `ClawBotClient` SDK 的自定义机器人 |
| `http` | Webhook POST | 第三方服务、n8n、Zapier |

### SDK 客户端示例

```python
import asyncio
from wechat_clawbot.sdk import ClawBotClient

async def main():
    async with ClawBotClient(
        gateway_url="http://localhost:8765",
        endpoint_id="my-bot",
    ) as client:
        async for msg in client.messages():
            print(f"来自 {msg.sender_id}: {msg.text}")
            await client.reply(msg.sender_id, f"回声: {msg.text}")

asyncio.run(main())
```

### Admin API

Admin API 运行在 `admin_port`（默认 8766），设置 `admin_token` 时启用 Bearer Token 认证。

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/status` | 网关状态概览 |
| GET | `/api/accounts` | 列出 Bot 账户 |
| GET | `/api/endpoints` | 列出端点及状态 |
| POST | `/api/endpoints` | 添加端点 |
| DELETE | `/api/endpoints/{id}` | 删除端点 |
| GET | `/api/users` | 列出用户 |
| POST | `/api/users/{id}/bind` | 绑定用户到端点 |
| POST | `/api/users/{id}/unbind` | 解绑用户与端点 |
| GET | `/api/invites` | 列出邀请码 |
| POST | `/api/invites` | 创建邀请码 |

### CLI 参考

| 命令 | 说明 |
|------|------|
| `clawbot-gateway init` | 初始化配置 |
| `clawbot-gateway start` | 启动网关 |
| `clawbot-gateway stop` | 停止网关 |
| `clawbot-gateway status` | 查看网关状态 |
| `clawbot-gateway account add` | 扫码添加 Bot 账户 |
| `clawbot-gateway account list` | 列出已配置账户 |
| `clawbot-gateway account remove <id>` | 删除账户 |
| `clawbot-gateway account status [id]` | 查看账户状态 |
| `clawbot-gateway endpoint list` | 列出端点 |
| `clawbot-gateway endpoint add <id>` | 添加端点 |
| `clawbot-gateway endpoint remove <id>` | 删除端点 |
| `clawbot-gateway user list` | 列出所有用户 |
| `clawbot-gateway user info <id>` | 查看用户信息 |
| `clawbot-gateway user allow <id>` | 允许用户访问 |
| `clawbot-gateway user block <id>` | 屏蔽用户 |
| `clawbot-gateway user bind <uid> <eid>` | 绑定用户到端点 |
| `clawbot-gateway user unbind <uid> <eid>` | 解绑用户与端点 |
| `clawbot-gateway invite list` | 列出活跃邀请码 |
| `clawbot-gateway invite create <eid>` | 创建邀请码 |
| `clawbot-gateway logs` | 查看消息归档日志 |

所有命令支持 `--json` 输出机器可读格式，`--gateway <url>` 连接远程网关管理。

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
  gateway/          # M:N 路由网关 (v0.4.0+)
    channels/       #   子通道实现（MCP、SDK、HTTP）
    admin.py        #   Admin HTTP API 服务器
    app.py          #   网关主编排器
    cli.py          #   CLI 入口（clawbot-gateway）
    config.py       #   gateway.yaml 配置 Schema 和加载器
    delivery.py     #   SQLite 投递队列
    router.py       #   消息路由引擎
    session.py      #   用户会话/状态持久化
  sdk/              # ClawBotClient 客户端库（自定义机器人）
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
