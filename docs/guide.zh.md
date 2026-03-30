# WeChat ClawBot 使用指南

[English](guide.md) | 中文

基于实际场景的操作指南，涵盖部署、日常运维、维护和开发。按使用者角色和目标分类。

---

## 场景一：个人开发者 — Claude Code + 微信

最简单的用法：你是一个独立开发者，希望 Claude Code 能接收并回复微信消息。

### 前置条件

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)（推荐）或 pip
- 一个有 ClawBot iLink 平台访问权限的微信账号
- 已安装 Claude Code CLI（`npm install -g @anthropic-ai/claude-code`）

### 第一步：安装 wechat-clawbot

```bash
pip install wechat-clawbot
# 或用 uv：
uv add wechat-clawbot
```

此场景无需额外依赖，核心包已包含单通道模式所需的全部组件。

### 第二步：微信扫码登录

```bash
wechat-clawbot-cc setup
```

终端中会显示一个二维码。打开手机微信扫描即可完成认证，凭据自动保存到 `~/.claude/channels/wechat/account.json`。

### 第三步：注册 MCP 服务器

```bash
claude mcp add wechat -- wechat-clawbot-cc serve
```

这会告诉 Claude Code 有一个名为 "wechat" 的 MCP 服务器可供连接。

### 第四步：启动 Claude Code + 微信通道

```bash
claude --dangerously-load-development-channels server:wechat
```

Claude Code 启动并开始监听微信消息。当有人给你的 ClawBot 发消息时，Claude 会看到消息并通过 `wechat_reply` 工具回复。

### 验证是否正常工作

1. 打开微信，找到 ClawBot 的对话
2. 发送一条测试消息，比如 "你好"
3. 在 Claude Code 终端中，你应该能看到消息以通道通知的形式出现
4. Claude 会回复，回复内容出现在微信聊天中

### Claude Code 中可用的工具

连接后，Claude Code 可以使用三个工具：

| 工具 | 说明 |
|------|------|
| `wechat_reply` | 向微信用户发送文字回复 |
| `wechat_send_file` | 向微信用户发送文件（图片、视频、文档） |
| `wechat_typing` | 向微信用户显示"正在输入"状态 |

### 常见问题

| 问题 | 解决方案 |
|------|----------|
| 二维码过期 | 重新运行 `wechat-clawbot-cc setup` |
| "未找到凭据" | 在 `serve` 之前先运行 `wechat-clawbot-cc setup` |
| 收不到消息 | 确认启动 Claude Code 时使用了 `--dangerously-load-development-channels server:wechat` |
| 消息突然中断 | 会话可能已过期，重新运行 `wechat-clawbot-cc setup` |

---

## 场景二：个人开发者 — Codex + 微信

目标与场景一相同，但使用 OpenAI Codex 代替 Claude Code。

### 与 Claude Code 的差异

Codex 不支持 MCP 通道推送通知。桥接适配器通过轮询机制工作：

1. 新消息到达时，桥接器发送 `notifications/resources/updated` 通知给 Codex
2. Codex 调用 `wechat_get_messages` 工具获取待处理消息
3. Codex 调用 `wechat_reply` 发送回复

### 直连模式设置

```bash
# 安装
pip install wechat-clawbot

# 扫码登录
wechat-clawbot-cc setup

# 为 Codex 注册 MCP 服务器
codex mcp add wechat -- wechat-clawbot-cc serve
```

### 桥接模式设置（通过网关）

如果你已经运行了网关（参见场景三），使用桥接模式：

```bash
codex mcp add wechat -- wechat-clawbot-cc serve --gateway http://localhost:8765 --endpoint my-project
```

### `wechat_get_messages` 工作原理

桥接模式下会自动提供此工具。调用时，它会取出队列中所有待处理消息并以通道标记格式返回：

```xml
<channel source="wechat" sender="user123@im.wechat" sender_id="user123@im.wechat">
你好，可以帮我一下吗？
</channel>
```

为了让 Codex 主动检查消息，可以在提示词中加入类似说明：

> "当你收到 wechat://messages/pending 的资源更新通知时，调用 wechat_get_messages 查看新的微信消息。"

### 可用工具

场景一中的所有工具，加上：

| 工具 | 说明 |
|------|------|
| `wechat_get_messages` | 获取并返回所有待处理的微信消息（仅桥接模式） |

---

## 场景三：团队部署 — 网关 + 多个 AI 后端

> **微信 Bot 约束：** 每个微信账号只能创建一个 Bot，且该 Bot 与创建者的微信账号一对一绑定（1:1）。多人无法共享同一个 Bot。网关管理多个 Bot（每个属于不同微信用户），将消息路由到多个端点。

你需要搭建一个网关，将一个或多个微信 Bot 账户的消息路由到多个 AI 后端。每个 Bot 属于不同的微信用户。开发者将自己的 Claude Code 或 Codex 实例作为独立端点连接到网关。

### 规划

开始之前，先确定以下事项：

- **需要几个微信 Bot 账户？** 每个微信账号只能创建一个 Bot，且一对一绑定。单人使用网关管理多个项目端点只需一个 Bot；团队多人协作则每人各自一个 Bot（一个微信号 = 一个 Bot）。
- **端点如何命名？** 按项目或团队成员命名（如 `project-alpha`、`alice-claude`、`support-bot`）。
- **访问控制策略：** `open`（任何人可用）、`allowlist`（仅预授权用户）、`invite-code`（用户需兑换邀请码）。
- **服务器：** 网关需要运行在微信（公网）和开发者（内网）都能访问的机器上。

### 第一步：安装并初始化

在服务器上：

```bash
pip install "wechat-clawbot[gateway]"

clawbot-gateway init
```

这会在 `~/.clawbot-gateway/gateway.yaml` 创建一份模板配置文件。

### 第二步：添加微信 Bot 账户

```bash
clawbot-gateway account add
```

用微信扫描二维码。凭据保存到 `~/.clawbot-gateway/accounts/<account-id>.json`。

### 第三步：配置网关

编辑 `~/.clawbot-gateway/gateway.yaml`：

```yaml
# ---- 服务器配置 ----------------------------------------------------------------
gateway:
  host: 0.0.0.0          # 监听所有网络接口
  port: 8765              # 主网关端口（MCP SSE、SDK WS、HTTP 回调）
  admin_port: 8766        # 管理 API 端口（独立端口，便于防火墙隔离）
  admin_token: "s3cret-t0ken-ch4nge-me"   # 管理 API 认证令牌
  log_level: info

# ---- 微信 Bot 账户（下游）-----------------------------------------------------
accounts:
  team-bot:
    credentials: ~/.clawbot-gateway/accounts/team-bot.json

# ---- 上游端点 ------------------------------------------------------------------
endpoints:
  project-alpha:
    name: "Alpha 项目"
    type: mcp               # Claude Code 用户使用
    description: "Alpha 团队 Claude Code 端点"

  project-beta:
    name: "Beta 项目"
    type: mcp               # 另一个 MCP 端点
    description: "Beta 团队 Claude Code 端点"

  support-bot:
    name: "客服机器人"
    type: sdk               # Python 自定义机器人
    description: "自动客服回复"

  analytics-webhook:
    name: "数据分析"
    type: http              # 外部服务 Webhook
    url: "https://your-service.example.com/wechat-webhook"
    api_key: "webhook-secret-key"
    description: "将消息转发到数据分析管道"

# ---- 路由 ----------------------------------------------------------------------
routing:
  strategy: active-endpoint     # 用户自行选择活跃端点
  mention_prefix: "@"           # @端点名称 可以发送到指定端点
  gateway_commands:
    - "/"                       # 斜杠命令如 /list、/use、/help

# ---- 授权 ----------------------------------------------------------------------
authorization:
  mode: invite-code             # 用户需要邀请码才能加入
  default_endpoints:
    - project-alpha             # 新用户自动绑定到此端点
  admins:
    - "your-wechat-id@im.wechat"   # 你的微信用户 ID（可在日志中查看）

# ---- 消息归档（可选）------------------------------------------------------------
archive:
  enabled: true
  path: ~/.clawbot-gateway/archive.db
  retention_days: 30            # 保留 30 天消息记录
```

### 第四步：启动网关

```bash
clawbot-gateway start
```

网关开始在 8765 端口（主服务）和 8766 端口（管理 API）监听。

### 第五步：各开发者连接客户端

**开发者使用 Claude Code（桥接模式）：**

```bash
# 注册指向网关的 MCP 服务器
claude mcp add wechat -- wechat-clawbot-cc serve \
  --gateway http://your-server:8765 \
  --endpoint project-alpha \
  --api-key s3cret-t0ken-ch4nge-me

# 启动 Claude Code + 微信通道
claude --dangerously-load-development-channels server:wechat
```

**开发者使用 Codex（桥接模式）：**

```bash
codex mcp add wechat -- wechat-clawbot-cc serve \
  --gateway http://your-server:8765 \
  --endpoint project-beta \
  --api-key s3cret-t0ken-ch4nge-me
```

**开发者运行自定义机器人（SDK）：**

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
            print(f"来自 {msg.sender_id}: {msg.text}")
            await client.reply(msg.sender_id, f"感谢您的消息！")

asyncio.run(main())
```

### 第六步：用户接入

由于网关配置为 `invite-code` 模式，需要创建邀请码并分享给团队成员：

```bash
# 创建邀请码：绑定到 project-alpha，10 次使用，48 小时过期
clawbot-gateway invite create project-alpha --max-uses 10 --ttl 48 \
  --gateway http://your-server:8766 \
  --admin-token s3cret-t0ken-ch4nge-me
```

将邀请码分享给团队成员，他们在微信中发送：

```
/bind <invite-code>
```

### 第七步：日常管理

```bash
# 查看网关状态
clawbot-gateway status --gateway http://your-server:8766 --admin-token s3cret-t0ken-ch4nge-me

# 列出所有用户
clawbot-gateway user list --gateway http://your-server:8766 --admin-token s3cret-t0ken-ch4nge-me

# 查看最近消息
clawbot-gateway logs -n 20 --gateway http://your-server:8766 --admin-token s3cret-t0ken-ch4nge-me
```

为了避免每次都输入网关地址和令牌，使用环境变量：

```bash
export CLAWBOT_GATEWAY_URL=http://your-server:8766
export CLAWBOT_ADMIN_TOKEN=s3cret-t0ken-ch4nge-me

# 现在命令更简洁：
clawbot-gateway status
clawbot-gateway user list
clawbot-gateway logs -n 20
```

---

## 场景四：邀请码工作流

邀请码系统让管理员无需维护静态白名单即可控制用户访问。

### 工作流程

1. 管理员创建一个绑定到特定端点的邀请码
2. 管理员将邀请码分享给团队成员（通过 Slack、邮件等）
3. 团队成员在微信 ClawBot 对话中发送 `/bind <邀请码>`
4. 网关验证邀请码，将用户绑定到对应端点，并返回确认信息

### 创建邀请码

```bash
# 基础用法：单次使用，永不过期
clawbot-gateway invite create project-alpha

# 5 次使用，24 小时过期
clawbot-gateway invite create project-alpha --max-uses 5 --ttl 24

# 不限次数，72 小时过期
clawbot-gateway invite create project-alpha --max-uses 0 --ttl 72
```

### 查看活跃邀请码

```bash
clawbot-gateway invite list
```

输出包含邀请码、绑定端点、剩余次数和过期时间。

### 用户兑换邀请码

在微信中发送：

```
/bind aB3dEf_g
```

网关回复：

```
Bound to endpoint: Alpha 项目
```

### 授权模式对比

| 模式 | 行为 |
|------|------|
| `open` | 任何人都可以发消息，无需邀请 |
| `allowlist` | 仅 `admins` 列表中的用户或预注册用户可以交互 |
| `invite-code` | 用户必须兑换邀请码才能获得访问权限；管理员始终有权限 |

### 配置方式

在 `gateway.yaml` 中：

```yaml
authorization:
  mode: invite-code
  default_endpoints:
    - project-alpha       # 用户首次交互时自动绑定到这些端点
  admins:
    - "admin@im.wechat"  # 管理员无需邀请码
```

---

## 场景五：自定义机器人开发（SDK）

你想用 Python 构建一个自定义微信机器人。SDK 提供了一个简洁的 WebSocket 客户端，连接到网关即可收发消息。

### 安装

```bash
pip install "wechat-clawbot[sdk]"
```

### 完整示例：回声机器人

```python
import asyncio
from wechat_clawbot.sdk import ClawBotClient

async def main():
    async with ClawBotClient(
        gateway_url="http://localhost:8765",
        endpoint_id="echo-bot",
    ) as client:
        print("回声机器人已连接，等待消息...")
        async for msg in client.messages():
            print(f"[{msg.sender_id}] {msg.text}")
            await client.reply(msg.sender_id, f"回声: {msg.text}")

asyncio.run(main())
```

### ClawBotClient API

```python
ClawBotClient(
    gateway_url: str,       # 网关 HTTP 地址（如 "http://localhost:8765"）
    endpoint_id: str,       # 网关配置中的端点 ID
    token: str = "",        # 可选认证令牌
    reconnect: bool = True, # 断线自动重连
    reconnect_delay: float = 5.0,  # 重连间隔（秒）
)
```

**方法：**

| 方法 | 说明 |
|------|------|
| `await client.connect()` | 连接到网关 WebSocket |
| `await client.close()` | 关闭连接 |
| `async for msg in client.messages()` | 遍历接收到的消息 |
| `await client.reply(sender_id, text)` | 回复用户 |
| `await client.ping()` | 发送心跳保活 |

**Message 对象：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `sender_id` | `str` | 微信用户 ID（如 `user@im.wechat`） |
| `text` | `str` | 消息文本内容 |
| `context_token` | `str | None` | 会话追踪令牌 |

### 处理不同类型的消息

SDK 目前以文本形式投递消息。媒体消息由网关转换为文本描述。根据消息内容可以进行不同处理：

```python
async for msg in client.messages():
    if msg.text.startswith("/"):
        # 处理机器人自定义命令
        command = msg.text.split()[0][1:]
        await handle_command(client, msg, command)
    elif "帮助" in msg.text:
        await client.reply(msg.sender_id, "可用命令：/info、/stats")
    else:
        await client.reply(msg.sender_id, f"回声: {msg.text}")
```

### 自动重连机制

WebSocket 连接断开时，客户端会自动重连。也可以禁用此功能：

```python
client = ClawBotClient(
    gateway_url="http://localhost:8765",
    endpoint_id="my-bot",
    reconnect=False,  # 断开时抛出异常而不是重连
)
```

### 网关中的 SDK 端点配置

在 `gateway.yaml` 中将端点类型设为 `sdk`：

```yaml
endpoints:
  echo-bot:
    name: "回声机器人"
    type: sdk
    description: "用于测试的简单回声机器人"
```

---

## 场景六：第三方 Webhook 集成

你想将外部服务（Dify、n8n、Zapier 或任何支持 HTTP 的系统）接入微信消息收发。

### 工作原理

1. **入站消息：** 网关将每条消息以 JSON 格式 POST 到你服务的 Webhook URL
2. **同步回复：** 你的服务可以在 HTTP 响应体中包含回复内容
3. **异步回复：** 你的服务可以稍后通过网关的回调 URL 发送回复

### 第一步：配置 HTTP 端点

在 `gateway.yaml` 中：

```yaml
endpoints:
  my-webhook:
    name: "Webhook 服务"
    type: http
    url: "https://your-service.example.com/wechat/inbound"
    api_key: "your-webhook-secret"
```

### 第二步：接收消息

网关向你的 URL 发送 POST 请求，载荷格式：

```json
{
  "sender_id": "user123@im.wechat",
  "text": "你好，我想查一下订单",
  "context_token": "tok_abc123..."
}
```

请求头：
- `Content-Type: application/json`
- `Authorization: Bearer your-webhook-secret`（当配置了 `api_key` 时）

### 第三步：同步回复

返回包含 `reply` 或 `text` 字段的 JSON 响应：

```json
{
  "reply": "感谢联系我们！您的订单正在处理中。"
}
```

网关会自动将此回复转发给微信用户。

### 第四步：异步回复（通过回调）

如果你的服务需要更多时间处理，先返回 200 OK（不含回复），之后再通过回调 URL 发送：

```
POST http://your-gateway:8765/http/my-webhook/callback
Content-Type: application/json
Authorization: Bearer your-webhook-secret

{
  "sender_id": "user123@im.wechat",
  "text": "您的订单 #12345 已发货！"
}
```

### 认证机制

端点配置中的 `api_key` 有双重作用：
- **出站请求：** 网关向你的 URL 发送 POST 时，附带 `Authorization: Bearer <api_key>` 头
- **入站回调：** 你的服务向 `/http/{id}/callback` 发送 POST 时，需要携带同样的 Bearer 令牌

### 示例：n8n 集成

1. 在 n8n 中创建一个 Webhook 触发器节点
2. 将 Webhook URL 设置为 gateway.yaml 中的端点 URL
3. 在 n8n 工作流中处理消息
4. 使用 HTTP Request 节点向回调 URL 发送回复

### 示例：Flask Webhook 服务

```python
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/wechat/inbound", methods=["POST"])
def handle_message():
    data = request.json
    sender = data["sender_id"]
    text = data["text"]

    # 处理消息
    reply_text = generate_response(text)

    return jsonify({"reply": reply_text})

def generate_response(text):
    return f"已收到: {text}"

if __name__ == "__main__":
    app.run(port=5000)
```

---

## 场景七：远程网关管理

你有一个运行在远程服务器上的网关，需要从本地机器进行管理。

### 方式一：使用 --gateway 参数

每个 CLI 命令都支持 `--gateway` 和 `--admin-token` 参数：

```bash
clawbot-gateway status \
  --gateway http://my-server:8766 \
  --admin-token s3cret-t0ken

clawbot-gateway user list \
  --gateway http://my-server:8766 \
  --admin-token s3cret-t0ken
```

### 方式二：使用环境变量

设置一次，所有命令自动生效：

```bash
export CLAWBOT_GATEWAY_URL=http://my-server:8766
export CLAWBOT_ADMIN_TOKEN=s3cret-t0ken

# 之后直接使用命令：
clawbot-gateway status
clawbot-gateway user list
clawbot-gateway endpoint list
clawbot-gateway logs -n 50
```

### 常用管理操作

**检查网关是否运行：**

```bash
clawbot-gateway status
```

输出：

```json
{
  "status": "running",
  "accounts": 1,
  "endpoints": { "total": 3, "online": 2 },
  "users": 12
}
```

**列出所有端点及状态：**

```bash
clawbot-gateway endpoint list
```

**查看特定用户信息：**

```bash
clawbot-gateway user info "user123@im.wechat"
```

**管理员绑定用户到端点：**

```bash
clawbot-gateway user bind "user123@im.wechat" project-alpha
```

**解绑用户与端点：**

```bash
clawbot-gateway user unbind "user123@im.wechat" project-alpha
```

**运行时添加新端点（无需重启）：**

```bash
clawbot-gateway endpoint add new-endpoint \
  --name "新端点" \
  --type mcp
```

**删除端点：**

```bash
clawbot-gateway endpoint remove old-endpoint
```

**查看消息日志：**

```bash
# 最近 50 条消息（默认）
clawbot-gateway logs

# 指定端点的最近 100 条消息
clawbot-gateway logs -n 100 --endpoint project-alpha

# 指定用户的消息
clawbot-gateway logs --user "user123@im.wechat"
```

### JSON 输出

任何命令都可以加 `--json` 获取机器可读的输出，便于脚本处理：

```bash
clawbot-gateway status --json | jq '.endpoints.online'
```

---

## 场景八：监控与维护

网关日常运维操作指南。

### 查看网关状态

```bash
clawbot-gateway status
```

显示内容包括：
- 网关进程是否运行中
- 已连接的账户数量
- 端点总数及在线数
- 已知用户数量

### 查看消息日志

需要在 gateway.yaml 中启用消息归档（`archive.enabled: true`）：

```bash
# 最近消息
clawbot-gateway logs -n 20

# 按端点过滤
clawbot-gateway logs --endpoint project-alpha -n 50

# 按用户过滤
clawbot-gateway logs --user "user123@im.wechat" -n 50

# JSON 输出用于进一步处理
clawbot-gateway logs --json | jq '.messages[] | select(.direction == "inbound")'
```

### 端点健康监控

端点有三种状态：
- **online** — 客户端已连接且活跃
- **offline** — 无客户端连接
- **error** — 连接已建立但遇到错误

```bash
# 概览
clawbot-gateway endpoint list

# 详细状态（通过管理 API）
clawbot-gateway status --json | jq '.endpoints'
```

### 处理会话过期

微信 Bot 会话会定期过期。过期时：
- 网关检测到过期后暂停该账户的消息轮询
- 该账户上的消息接收停止
- 暂停期（默认 60 秒）后网关会自动重试

如果会话永久过期：

```bash
# 重新扫码登录
clawbot-gateway account add
```

然后重启网关：

```bash
clawbot-gateway stop
clawbot-gateway start
```

### 优雅停止

网关支持 SIGINT 和 SIGTERM 信号的优雅关闭：

```bash
# 通过 PID 文件停止
clawbot-gateway stop

# 或直接发送信号
kill -SIGINT $(cat ~/.clawbot-gateway/gateway.pid)
```

### 日志文件

网关将应用日志输出到 stderr（服务进程的标准做法）。如需持久化日志，重定向输出：

```bash
clawbot-gateway start 2>&1 | tee -a /var/log/clawbot-gateway.log
```

微信客户端还会将 JSON 行格式的日志写入 `/tmp/openclaw/openclaw-YYYY-MM-DD.log`。

### 清理过期数据

邀请码在过期或用尽后会自动清除。消息归档的保留时间由配置控制：

```yaml
archive:
  enabled: true
  retention_days: 30    # 自动删除 30 天前的消息
                        # 0 = 永久保留
```

---

## 场景九：开发与扩展网关

面向希望贡献代码或定制功能的开发者。

### 项目结构概览

```
src/wechat_clawbot/
  api/                  # ilink HTTP API 客户端和协议类型
  auth/                 # QR 登录、账户存储、凭证管理
  cdn/                  # AES-128-ECB CDN 上传/下载管道
  claude_channel/       # Claude Code MCP Channel 桥接
    cli.py              #   CLI（wechat-clawbot-cc）
    bridge.py           #   桥接模式（网关 SSE -> MCP stdio）
    server.py           #   直连模式（微信轮询 -> MCP stdio）
    credentials.py      #   凭据存储（~/.claude/channels/wechat/）
    setup.py            #   交互式扫码登录
  config/               # Pydantic 配置 Schema
  gateway/              # 多 Bot、多端点路由网关
    channels/           #   子通道实现
      base.py           #     SubChannel 协议 + 回调类型定义
      mcp_channel.py    #     MCP SSE 子通道
      sdk_channel.py    #     WebSocket SDK 子通道
      http_channel.py   #     HTTP Webhook 子通道
    admin.py            #   管理 HTTP API（Starlette）
    app.py              #   网关主编排器（GatewayApp）
    cli.py              #   CLI 入口（clawbot-gateway）
    config.py           #   gateway.yaml 配置 Schema 和加载器
    commands.py         #   微信聊天命令处理器
    delivery.py         #   SQLite 投递队列
    router.py           #   消息路由引擎
    session.py          #   用户会话/状态持久化
    endpoint_manager.py #   端点注册与健康监测
    invite.py           #   邀请码系统
    auth.py             #   授权模块
    archive.py          #   消息归档（SQLite）
    db.py               #   AsyncSQLiteStore 基类
    types.py            #   核心数据类和枚举
  media/                # 媒体下载、MIME 类型、SILK 转码
  messaging/            # 入站消息转换、发送管道、斜杠命令
    mcp_defs.py         #   共享 MCP 工具定义
  monitor/              # 长轮询监控循环
  sdk/                  # ClawBotClient 客户端库（自定义机器人）
  storage/              # 状态目录、同步缓冲区持久化
  util/                 # 日志、ID 生成、敏感字段脱敏
```

### 核心开发规范

- **anyio 异步** — 所有 I/O 操作使用 anyio 实现结构化并发（非原生 asyncio）
- **Pydantic 配置** — 配置模型使用 Pydantic v2，支持验证
- **dataclass 运行时类型** — `types.py` 使用 `@dataclass` 定义运行时数据结构
- **SQLite WAL 模式** — 投递队列和归档使用 WAL 模式 SQLite，通过 `AsyncSQLiteStore` 封装
- **线程卸载** — SQLite 操作通过 `anyio.to_thread.run_sync` 在工作线程中执行
- **Starlette HTTP** — 网关和管理 API 使用 Starlette ASGI 框架
- **微信回复禁止 Markdown** — 网关命令的响应使用纯文本（微信不渲染 Markdown）
- **Ruff 代码检查** — 在 `pyproject.toml` 中配置，目标版本 Python 3.10+

### 添加新的子通道类型

1. 创建 `src/wechat_clawbot/gateway/channels/my_channel.py`
2. 实现 `base.py` 中定义的 `SubChannel` 协议：

```python
from .base import ReplyCallback

class MyChannel:
    def __init__(self, on_reply: ReplyCallback) -> None:
        self._on_reply = on_reply

    async def start(self) -> None:
        """初始化通道（建立连接等）。"""
        ...

    async def stop(self) -> None:
        """清理资源。"""
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
        """投递消息到端点。成功返回 True。"""
        ...

    async def send_reply(
        self,
        endpoint_id: str,
        sender_id: str,
        text: str,
        context_token: str | None = None,
    ) -> None:
        """通过此通道发送回复。"""
        ...

    def is_endpoint_connected(self, endpoint_id: str) -> bool:
        ...

    def get_connected_endpoints(self) -> list[str]:
        ...
```

3. 在 `types.py` 的 `ChannelType` 枚举中注册新类型
4. 在 `app.py` 的 `GatewayApp.start()` 中接入新通道

### 添加新的网关命令

1. 打开 `src/wechat_clawbot/gateway/commands.py`
2. 添加处理函数：

```python
async def _handle_mycommand(ctx: GatewayCommandContext) -> str:
    """处理 /mycommand 命令。"""
    return "这是我的自定义命令！"
```

3. 在文件末尾的 `HANDLERS` 字典中注册：

```python
HANDLERS.update({
    # ... 已有处理器 ...
    "mycommand": _handle_mycommand,
})
```

4. 如有必要，更新 `GATEWAY_COMMANDS` frozenset

### 运行测试套件

```bash
# 克隆并初始化
git clone https://github.com/nightsailer/wechat-clawbot.git
cd wechat-clawbot
uv sync

# 运行全部测试
uv run pytest tests/ -v

# 运行指定测试文件
uv run pytest tests/test_gateway.py -v

# 带覆盖率运行
uv run pytest tests/ --cov=wechat_clawbot

# 代码检查
uv run ruff check src/ tests/

# 代码格式化
uv run ruff format src/ tests/

# 完整预提交检查
uv run ruff check src/ tests/ && uv run ruff format src/ tests/
```

### 代码风格

- 导入顺序：标准库、第三方、本地 — 用空行分隔
- 类型注解：所有公开函数必须标注
- 文档字符串：所有公开类和函数必须编写
- 行长度：在 `pyproject.toml` 中通过 Ruff 配置
- 所有模块使用 `from __future__ import annotations`

---

## 附录 A：完整 CLI 参考与示例

### 全局参数

所有 `clawbot-gateway` 命令均支持以下参数：

| 参数 | 说明 |
|------|------|
| `--config <路径>` | gateway.yaml 路径（默认：`~/.clawbot-gateway/gateway.yaml`） |
| `--json` | 以 JSON 格式输出 |
| `--yes`、`-y` | 跳过确认提示 |
| `--gateway <URL>` | 远程网关管理 URL（或设置 `CLAWBOT_GATEWAY_URL`） |
| `--admin-token <令牌>` | 管理 API Bearer 令牌（或设置 `CLAWBOT_ADMIN_TOKEN`） |

### init — 初始化配置

```bash
# 创建默认的 gateway.yaml
clawbot-gateway init
```

如果文件不存在，在 `~/.clawbot-gateway/gateway.yaml` 创建模板配置文件，并提示后续步骤。

### start — 启动网关

```bash
# 使用默认配置启动
clawbot-gateway start

# 指定配置文件路径
clawbot-gateway start --config /etc/clawbot/gateway.yaml
```

启动后写入 PID 文件到 `~/.clawbot-gateway/gateway.pid`。支持 SIGINT/SIGTERM 优雅关闭。

### stop — 停止网关

```bash
clawbot-gateway stop
```

读取 PID 文件并向网关进程发送 SIGINT 信号。

### status — 查看网关状态

```bash
# 本地状态（读取配置文件 + PID 文件）
clawbot-gateway status

# 远程状态（查询管理 API）
clawbot-gateway status --gateway http://server:8766
```

### 账户管理

```bash
# 添加新 Bot 账户（交互式扫码登录）
clawbot-gateway account add

# 列出所有已配置账户
clawbot-gateway account list

# 从远程网关列出账户
clawbot-gateway account list --gateway http://server:8766

# 查看账户状态（需要运行中的网关）
clawbot-gateway account status
clawbot-gateway account status main-bot

# 删除账户（需手动编辑配置文件）
clawbot-gateway account remove old-bot
```

### 端点管理

```bash
# 列出所有端点（本地）
clawbot-gateway endpoint list

# 列出端点（远程）
clawbot-gateway endpoint list --gateway http://server:8766

# 添加 MCP 端点
clawbot-gateway endpoint add claude-dev --name "Claude 开发" --type mcp \
  --gateway http://server:8766

# 添加 SDK 端点
clawbot-gateway endpoint add custom-bot --name "自定义机器人" --type sdk \
  --gateway http://server:8766

# 添加 HTTP Webhook 端点
clawbot-gateway endpoint add webhook --name "Webhook" --type http \
  --url https://example.com/hook \
  --gateway http://server:8766

# 删除端点
clawbot-gateway endpoint remove old-endpoint --gateway http://server:8766
```

### 用户管理

```bash
# 列出所有已知用户
clawbot-gateway user list

# 查看特定用户信息
clawbot-gateway user info "user123@im.wechat"

# 管理员绑定用户到端点
clawbot-gateway user bind "user123@im.wechat" project-alpha

# 解绑用户与端点
clawbot-gateway user unbind "user123@im.wechat" project-alpha

# 允许用户访问（编辑 gateway.yaml 的 admins 列表）
clawbot-gateway user allow "user123@im.wechat"

# 屏蔽用户（编辑 gateway.yaml 的 admins 列表）
clawbot-gateway user block "user123@im.wechat"
```

**场景：新成员加入团队**

```bash
# 1. 创建邀请码
clawbot-gateway invite create project-alpha --max-uses 1 --ttl 24

# 2. 将邀请码分享给新成员
# 3. 新成员在微信中发送：/bind <邀请码>

# 4. 确认已连接
clawbot-gateway user list --json | jq '.users[] | select(.user_id | contains("new-user"))'
```

**场景：成员离开团队**

```bash
# 从所有端点解绑
clawbot-gateway user unbind "user@im.wechat" project-alpha
clawbot-gateway user unbind "user@im.wechat" project-beta
```

**场景：将用户切换到其他端点**

```bash
# 先解绑旧端点，再绑定新端点
clawbot-gateway user unbind "user@im.wechat" project-alpha
clawbot-gateway user bind "user@im.wechat" project-beta
```

### 邀请码管理

```bash
# 列出所有活跃邀请码
clawbot-gateway invite list

# 创建单次使用的邀请码（默认）
clawbot-gateway invite create project-alpha

# 创建多次使用且有过期时间的邀请码
clawbot-gateway invite create project-alpha --max-uses 10 --ttl 48

# 创建无限制邀请码（不限次数、不过期）
clawbot-gateway invite create project-alpha --max-uses 0 --ttl 0
```

**场景：为 project-x 接入 5 名团队成员**

```bash
# 创建一个 5 次使用、24 小时过期的邀请码
clawbot-gateway invite create project-x --max-uses 5 --ttl 24

# 输出：{"code": "aB3dEf_g", "endpoint_id": "project-x"}

# 分享邀请码："在微信中发送 /bind aB3dEf_g 即可加入 project-x"

# 监控使用情况
clawbot-gateway invite list --json | jq '.invites[] | select(.endpoint_id == "project-x")'
```

### 日志查看

```bash
# 查看最近 50 条消息（默认）
clawbot-gateway logs

# 查看最近 100 条消息
clawbot-gateway logs -n 100

# 按端点过滤
clawbot-gateway logs --endpoint project-alpha

# 按用户过滤
clawbot-gateway logs --user "user123@im.wechat"

# 组合过滤
clawbot-gateway logs --endpoint project-alpha --user "user123@im.wechat" -n 20

# JSON 输出用于脚本处理
clawbot-gateway logs --json -n 10
```

---

## 附录 B：配置参考

`gateway.yaml` 中每个字段的完整说明。

### `gateway` 部分

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `host` | string | `"0.0.0.0"` | 监听的 IP 地址。`0.0.0.0` 表示所有接口，`127.0.0.1` 仅本机。 |
| `port` | int | `8765` | 主网关端口。提供 MCP SSE（`/mcp/{id}/sse`）、SDK WebSocket（`/sdk/{id}/ws`）和 HTTP 回调（`/http/{id}/callback`）服务。 |
| `admin_port` | int | `8766` | 管理 API 端口。提供 `/api/*` 端点。使用独立端口便于通过防火墙隔离管理访问。 |
| `admin_token` | string | `""` | 管理 API 的 Bearer 认证令牌。为空时管理 API 无认证保护（不建议在生产环境使用）。 |
| `log_level` | string | `"info"` | 日志详细程度。可选：`debug`、`info`、`warning`、`error`。 |

### `accounts` 部分

微信 Bot 账户的字典。键为账户 ID（自定义名称）。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `credentials` | string 或 null | `null` | 凭据 JSON 文件路径（由 `clawbot-gateway account add` 创建）。支持 `~` 展开。 |
| `token` | string 或 null | `null` | 内联 Bot 令牌（凭据文件的替代方案）。 |
| `base_url` | string | `"https://ilinkai.weixin.qq.com"` | iLink API 基础 URL。仅在需要连接自定义服务器时修改。 |

每个账户必须提供 `credentials` 或 `token` 其中之一。推荐使用凭据文件方式。

### `endpoints` 部分

上游端点的字典。键为端点 ID。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | string | `""` | 用于显示的名称，在 `/list` 命令中展示。为空时使用端点 ID。 |
| `type` | string | `"mcp"` | 通道类型：`mcp`、`sdk` 或 `http`。 |
| `url` | string | `""` | `http` 类型：消息 POST 目标 URL。`mcp`/`sdk` 类型：不使用（客户端主动连接网关）。 |
| `tags` | list[string] | `[]` | 用于端点分类的任意标签。 |
| `api_key` | string | `""` | `http` 类型：Webhook 认证 Bearer 令牌。`mcp`/`sdk` 类型：不使用。 |
| `description` | string | `""` | 端点描述，用于文档目的。 |

### `routing` 部分

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `strategy` | string | `"active-endpoint"` | 路由策略。`active-endpoint`：路由到用户选择的活跃端点。`prefix`：通过 @提及 前缀路由。`smart`：自动检测。 |
| `mention_prefix` | string | `"@"` | 按名称提及端点的前缀（如 `@claude 你好`）。 |
| `gateway_commands` | list[string] | `["/"]` | 触发网关命令（如 `/list`、`/use`、`/help`）的前缀。 |

### `authorization` 部分

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `mode` | string | `"allowlist"` | 授权模式：`open`、`allowlist` 或 `invite-code`。 |
| `default_endpoints` | list[string] | `[]` | 新用户自动绑定的端点 ID 列表。 |
| `admins` | list[string] | `[]` | 具有管理员权限的微信用户 ID。管理员不受授权限制，可使用 `/admin` 命令。 |

### `archive` 部分

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | `false` | 是否启用消息归档。启用后所有消息存储到 SQLite。 |
| `storage` | string | `"sqlite"` | 存储后端。目前仅支持 `sqlite`。 |
| `path` | string | `""` | 归档数据库文件路径。为空时默认为 `~/.clawbot-gateway/archive.db`。支持 `~` 展开。 |
| `retention_days` | int | `0` | 归档消息保留天数。`0` = 永久保留。 |

### 环境变量

| 变量 | 说明 |
|------|------|
| `CLAWBOT_GATEWAY_URL` | 默认网关管理 URL（替代 `--gateway` 参数） |
| `CLAWBOT_ADMIN_TOKEN` | 默认管理 API Bearer 令牌（替代 `--admin-token` 参数） |
| `CLAWBOT_GATEWAY_CONFIG` | gateway.yaml 路径（替代 `--config` 参数） |

---

## 附录 C：故障排查

### 二维码过期

**现象：** 扫码登录时二维码超时。

**解决方案：**

```bash
# 单通道模式：
wechat-clawbot-cc setup

# 网关模式：
clawbot-gateway account add
```

二维码有效期约 8 分钟，请尽快扫描。

### "端点未连接"

**现象：** 用户发送消息但没有回复；`/status` 显示端点为 offline。

**解决方案：** AI 客户端（Claude Code、Codex 或 SDK 机器人）未运行或无法连接到网关。

1. 确认客户端正在运行且已连接
2. 检查网关 URL 是否正确且可达
3. 桥接模式下，确认 `--gateway` 和 `--endpoint` 参数正确
4. 检查防火墙规则 — 网关端口必须对外开放

### "未授权"错误

**现象：** CLI 命令返回 `{"error": "unauthorized"}`。

**解决方案：**

```bash
# 确保 gateway.yaml 中的 admin_token 与 --admin-token 参数匹配
clawbot-gateway status --admin-token "correct-token"

# 或设置环境变量
export CLAWBOT_ADMIN_TOKEN="correct-token"
```

### 缺少依赖

**现象：** 启动时报 `ModuleNotFoundError`。

**解决方案：**

```bash
# 网关模式
pip install "wechat-clawbot[gateway]"

# SDK 客户端
pip install "wechat-clawbot[sdk]"

# 语音转码
pip install "wechat-clawbot[silk]"

# 所有扩展
pip install "wechat-clawbot[gateway,sdk,silk]"
```

### 桥接模式 "SSE 连接失败"

**现象：** 桥接日志显示 `SSE connection failed: 401` 或 `SSE connection error`。

**解决方案：**

1. 验证网关 URL 和端口：
   ```bash
   curl http://your-server:8765/mcp/your-endpoint/sse
   ```
2. 如果返回 401，说明 `--api-key` 与网关的 `admin_token` 不匹配
3. 如果连接被拒绝，检查网关是否在运行以及端口是否正确
4. 桥接器使用指数退避策略，会自动重试

### 消息未被投递

**现象：** 消息到达网关但没有转发到端点。

**可能原因：**

1. **用户未绑定端点：** 用户需要先发送 `/bind <端点>` 进行绑定
2. **活跃端点不对：** 用户当前的活跃端点不同，使用 `/use <名称>` 切换
3. **端点离线：** AI 客户端未连接，用 `/status` 查看状态
4. **授权被拒：** `allowlist` 模式下，用户可能未获授权

### 微信会话过期

**现象：** 网关停止接收消息；日志显示 `session expired` 或错误码 `-14`。

**解决方案：** 微信 Bot 会话已过期，这是正常现象。

```bash
# 重新认证
clawbot-gateway account add

# 重启网关
clawbot-gateway stop
clawbot-gateway start
```

### 网关无法启动

**现象：** `clawbot-gateway start` 立即退出并报错。

**常见原因：**

1. **YAML 语法错误：** 检查 `gateway.yaml` 的格式
2. **未定义账户：** 至少需要一个账户
3. **未定义端点：** 至少需要一个端点
4. **端口被占用：** 其他进程正在使用 8765 或 8766 端口

```bash
# 验证配置文件
python -c "from wechat_clawbot.gateway.config import load_gateway_config; load_gateway_config()"

# 检查端口是否被占用
lsof -i :8765
lsof -i :8766
```
