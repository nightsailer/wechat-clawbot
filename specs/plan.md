# Plan: Rewrite openclaw-weixin (TS) to wechat-clawbot (Python)

## Context

将 `@tencent-weixin/openclaw-weixin` TypeScript 包 (1.0.2) 等价重写为 Python 包 `wechat-clawbot`。
原始 TS 源码位于 `./vendors/openclaw-weixin/`。

## 技术栈

- **Python 3.10+**, `uv` 项目管理
- **pytest** 测试, **ruff** lint/format
- **httpx** (async HTTP client, 替代 Node fetch)
- **pydantic** (数据校验, 替代 zod)
- **qrcode** (终端二维码, 替代 qrcode-terminal)
- **cryptography** (AES-128-ECB, 替代 node:crypto)

## 项目结构

```
pyproject.toml                    # uv 项目配置 + ruff + pytest
src/wechat_clawbot/
├── __init__.py                   # 版本 + 公共 API
├── _version.py                   # __version__ = "0.1.0"
├── api/
│   ├── __init__.py
│   ├── client.py                 # ← api/api.ts (HTTP 客户端, httpx)
│   ├── types.py                  # ← api/types.ts (dataclass/pydantic)
│   ├── session_guard.py          # ← api/session-guard.ts
│   └── config_cache.py           # ← api/config-cache.ts
├── auth/
│   ├── __init__.py
│   ├── accounts.py               # ← auth/accounts.ts
│   ├── login_qr.py               # ← auth/login-qr.ts
│   └── pairing.py                # ← auth/pairing.ts
├── cdn/
│   ├── __init__.py
│   ├── aes_ecb.py                # ← cdn/aes-ecb.ts
│   ├── cdn_url.py                # ← cdn/cdn-url.ts
│   ├── download.py               # ← cdn/pic-decrypt.ts
│   └── upload.py                 # ← cdn/upload.ts + cdn/cdn-upload.ts
├── config/
│   ├── __init__.py
│   └── schema.py                 # ← config/config-schema.ts (pydantic)
├── media/
│   ├── __init__.py
│   ├── download.py               # ← media/media-download.ts
│   ├── mime.py                   # ← media/mime.ts
│   └── silk.py                   # ← media/silk-transcode.ts
├── messaging/
│   ├── __init__.py
│   ├── inbound.py                # ← messaging/inbound.ts
│   ├── send.py                   # ← messaging/send.ts
│   ├── send_media.py             # ← messaging/send-media.ts
│   ├── slash_commands.py         # ← messaging/slash-commands.ts
│   ├── debug_mode.py             # ← messaging/debug-mode.ts
│   ├── error_notice.py           # ← messaging/error-notice.ts
│   └── process_message.py        # ← messaging/process-message.ts
├── monitor/
│   ├── __init__.py
│   └── monitor.py                # ← monitor/monitor.ts
├── storage/
│   ├── __init__.py
│   ├── state_dir.py              # ← storage/state-dir.ts
│   └── sync_buf.py               # ← storage/sync-buf.ts
└── util/
    ├── __init__.py
    ├── logger.py                 # ← util/logger.ts
    ├── random.py                 # ← util/random.ts
    └── redact.py                 # ← util/redact.ts
tests/
├── __init__.py
├── test_aes_ecb.py
├── test_cdn_url.py
├── test_mime.py
├── test_redact.py
├── test_random.py
├── test_session_guard.py
├── test_inbound.py
├── test_send.py
├── test_accounts.py
├── test_debug_mode.py
├── test_slash_commands.py
└── test_state_dir.py
```

## 关键设计决策

### 1. 框架集成 → Protocol 抽象

TS 版本重度依赖 `openclaw/plugin-sdk`（路由、会话、回复分发、命令授权等）。
Python 版本在 `__init__.py` 中定义 `Protocol` 接口，核心业务逻辑完全独立可用。
`process_message.py` 中框架相关回调通过 `ProcessMessageDeps` dataclass 注入。

### 2. 异步模型

- 所有 I/O 操作使用 `async/await`（httpx.AsyncClient）
- Monitor 长轮询使用 `asyncio.Event` 替代 AbortSignal
- 文件 I/O 使用 `aiofiles` 或同步（小文件）

### 3. TS → Python 映射

| TypeScript | Python |
|---|---|
| `interface` / `type` | `@dataclass` / `TypedDict` |
| `zod` schema | `pydantic.BaseModel` |
| `fetch()` | `httpx.AsyncClient` |
| `Buffer` | `bytes` |
| `Map<K,V>` | `dict[str, ...]` |
| `AbortSignal` | `asyncio.Event` |
| `qrcode-terminal` | `qrcode` (terminal backend) |
| `node:crypto` AES | `cryptography` lib |
| `fs.readFileSync` | `pathlib.Path.read_text()` |
| `setTimeout` | `asyncio.sleep()` |

## 实施步骤

### Step 1: 项目脚手架
- `uv init` (已有 repo，只需 pyproject.toml)
- 配置 ruff, pytest
- 创建目录结构

### Step 2: 基础模块 (无外部依赖)
- `util/random.py`, `util/redact.py`, `util/logger.py`
- `storage/state_dir.py`, `storage/sync_buf.py`
- `cdn/aes_ecb.py`, `cdn/cdn_url.py`
- `media/mime.py`
- `api/types.py`

### Step 3: API 与认证
- `api/client.py` (httpx HTTP 客户端)
- `api/session_guard.py`
- `api/config_cache.py`
- `auth/accounts.py`
- `auth/login_qr.py`
- `auth/pairing.py`
- `config/schema.py`

### Step 4: CDN 与媒体
- `cdn/download.py`
- `cdn/upload.py`
- `media/download.py`
- `media/silk.py`

### Step 5: 消息处理
- `messaging/inbound.py`
- `messaging/send.py`
- `messaging/send_media.py`
- `messaging/debug_mode.py`
- `messaging/error_notice.py`
- `messaging/slash_commands.py`
- `messaging/process_message.py`

### Step 6: Monitor + Plugin 入口
- `monitor/monitor.py`
- `__init__.py` (公共 API 导出)

### Step 7: 测试
- 为每个独立模块编写 pytest 测试
- 使用 `pytest-asyncio` 测试异步函数
- 使用 `respx` mock httpx 请求

## 验证

```bash
uv run ruff check src/ tests/      # lint
uv run ruff format --check src/ tests/  # format check
uv run pytest tests/ -v              # 测试
```
