# 设计方案：Hub 多后端路由架构

## 背景

当前架构：一个微信 Bot 扫码 → 一个 MCP stdio server → 一个 Claude Code 实例（1:1 绑定）。

需求：一个微信 Bot 连接，后端接多个 Claude Code 实例。

## 架构概览

```
                        ┌─ Claude Code 实例A (MCP SSE)
微信 ←─ getUpdates ──→ Hub ──┼─ Claude Code 实例B (MCP SSE)
     ←─ sendmessage ──→     └─ Claude Code 实例C (MCP SSE)
```

Hub 是唯一持有微信 token 的进程，负责：
1. 维护微信长轮询连接（getUpdates）
2. 按路由规则分发消息到后端实例
3. 聚合各实例的 wechat_reply 调用，统一发送

## 路由策略

支持以下策略，通过配置文件选择：

### A. 按发送者路由（默认）

每个微信用户绑定到一个后端实例，同一用户的消息始终发往同一实例，保证上下文连续。

```yaml
routing:
  strategy: sender
  default_backend: coding
  bindings:
    "user_a@im.wechat": writing
    "user_b@im.wechat": coding
```

### B. 按指令前缀路由

消息以 `@name` 开头时路由到对应实例，无前缀走默认。

```yaml
routing:
  strategy: prefix
  default_backend: general
  prefixes:
    "@coder": coding
    "@writer": writing
```

### C. 广播 + 竞争

消息广播给所有实例，第一个调用 wechat_reply 的响应胜出，其余丢弃。
适用于多个专业 agent 竞争回答的场景。

### D. 轮询负载均衡

消息按顺序轮流分配给各实例。

## 传输方式

### 推荐：MCP SSE Transport

Hub 对外暴露 HTTP SSE 端点，Claude Code 通过 `claude mcp add` 连接：

```bash
# Hub 启动
wechat-clawbot-cc hub --config hub.yaml

# Claude Code 实例连接（可在不同机器上）
claude mcp add wechat --transport sse http://hub-host:8080/sse
```

优势：
- Claude Code 原生支持 MCP SSE transport
- 后端实例可分布在不同机器
- 动态增减实例无需重启 Hub
- 实例断线重连不影响其他实例

### 备选：多进程 stdio

Hub 作为父进程，fork 多个 MCP stdio 子进程。简单但不支持远程部署。

## 配置文件

`hub.yaml` 示例：

```yaml
# 微信连接（复用已有的 credentials）
wechat:
  credentials: ~/.claude/channels/wechat/account.json

# Hub 服务
hub:
  host: 0.0.0.0
  port: 8080

# 后端实例定义
backends:
  coding:
    description: "编程助手"
  writing:
    description: "写作助手"
  general:
    description: "通用助手"

# 路由规则
routing:
  strategy: sender          # sender | prefix | broadcast | round_robin
  default_backend: general
```

## 模块设计

### 新增模块

```
src/wechat_clawbot/hub/
├── __init__.py
├── hub.py              # Hub 主服务：轮询 + 路由 + SSE 端点
├── router.py           # 路由策略实现
├── backend.py          # 后端实例连接管理
└── config.py           # hub.yaml 配置解析
```

### 现有模块改造

| 模块 | 改动 |
|------|------|
| `claude_channel/server.py` | 拆分：轮询逻辑移入 hub，server 改为被动接收推送 |
| `claude_channel/cli.py` | 新增 `hub` 子命令 |
| `api/client.py` | 无改动，Hub 复用 |

## 数据流

### 入站（微信 → Claude Code）

```
1. Hub: getUpdates() 收到消息
2. Hub: router.route(msg) → 确定目标 backend
3. Hub: 通过 SSE 推送 channel notification 给目标实例
4. Claude Code: 收到消息，处理并回复
```

### 出站（Claude Code → 微信）

```
1. Claude Code: 调用 wechat_reply tool
2. Hub: 收到 tool call，查找 context_token
3. Hub: 调用 sendmessage API → 微信
4. Hub: 返回 "sent" 给 Claude Code
```

## 关键设计细节

### context_token 集中管理

context_token 必须由 Hub 集中管理，因为：
- 一个用户的 token 可能被多个实例使用（广播模式）
- 实例重启后 token 不丢失
- Hub 维护全局 LRU 缓存 + 可选持久化

### 实例健康检查

```python
class BackendManager:
    async def health_check(self) -> dict[str, bool]:
        """检查各实例连接状态"""

    async def on_disconnect(self, backend_id: str) -> None:
        """实例断线时，将其消息暂存或重路由"""
```

### 消息暂存

目标实例离线时，消息进入队列，实例重连后补发。避免消息丢失。

## 实施步骤

1. **Phase 1**: 抽取轮询逻辑为独立模块（从 server.py 解耦）
2. **Phase 2**: 实现 Hub 核心 + sender 路由策略
3. **Phase 3**: 实现 SSE transport 端点
4. **Phase 4**: 添加其他路由策略
5. **Phase 5**: 健康检查 + 消息暂存
