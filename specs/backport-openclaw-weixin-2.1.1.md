# Backport: openclaw-weixin 1.0.2 -> 2.1.1

> 日期: 2026-03-29
> 来源: `@tencent-weixin/openclaw-weixin@2.1.1`
> 目标: `wechat-clawbot` (Python port)

## 概述

从 openclaw-weixin 2.1.1 中提取了所有与 iLink 协议和功能相关的改进，backport 到本项目。
排除了 OpenClaw 框架自身的调整（SDK import 路径重构、宿主版本兼容检查、流式输出控制、多账号 cron 调度、日志上传等）。

## 忽略项（OpenClaw 自身调整）

- 所有 import 路径变更（`openclaw/plugin-sdk` -> `openclaw/plugin-sdk/core` 等）
- `compat.ts`（宿主版本兼容检查 `assertHostCompatibility`）
- `weixin-cli.ts`（OpenClaw 插件卸载命令）
- `registrationMode` 判断逻辑
- `blockStreaming` / `blockStreamingCoalesceDefaults` 流式输出控制
- `resolveOutboundAccountId` 多账号 cron 调度
- 删除 `log-upload.ts`（日志上传功能）
- 删除 `logUploadUrl` 配置项

---

## Phase 1: CDN full_url 支持 + Context Token 持久化（高优先级）

### 1.1 CDN full_url 直传支持

iLink API 现在可能直接返回完整的上传/下载 URL（`upload_full_url` / `full_url`），不再强制要求客户端通过 `encrypt_query_param` 拼接。

**修改文件:**

| 文件 | 改动说明 |
|---|---|
| `api/types.py` | `CDNMedia` 新增 `full_url` 字段；`GetUploadUrlResp` 新增 `upload_full_url` 字段；`_dict_to_cdn_media` 解析 `full_url` |
| `api/client.py` | `get_upload_url` 解析响应中的 `upload_full_url` |
| `cdn/cdn_url.py` | 新增 `ENABLE_CDN_URL_FALLBACK = True` 开关 |
| `cdn/download.py` | 新增 `_resolve_cdn_download_url()` 优先使用 `full_url`，fallback 到 `build_cdn_download_url`；`download_and_decrypt_buffer` 和 `download_plain_cdn_buffer` 增加 `full_url` 参数 |
| `cdn/upload.py` | `_upload_buffer_to_cdn` 支持 `upload_full_url` 优先于 `upload_param`；`_upload_media_to_cdn` 从 getUploadUrl 响应中提取 `upload_full_url` |
| `media/download.py` | 全部 4 种媒体类型（IMAGE/VOICE/FILE/VIDEO）支持 `full_url`；新增 `_has_downloadable_media` 检查两种 URL |
| `messaging/process_message.py` | `_find_main_media_item` 使用新的 `_has_downloadable_media()` 同时检查 `encrypt_query_param` 和 `full_url` |

### 1.2 Context Token 磁盘持久化

旧版 contextToken 仅在内存中保存，进程重启后丢失。新版将 token 持久化到磁盘文件 `{accountId}.context-tokens.json`。

**修改文件:**

| 文件 | 改动说明 |
|---|---|
| `messaging/inbound.py` | 新增 `_persist_context_tokens()`：每次收到新 token 时写入磁盘；新增 `restore_context_tokens()`：启动时从磁盘恢复到内存 map；新增 `clear_context_tokens_for_account()`：清除账号时同时删除磁盘文件；新增 `find_account_ids_by_context_token()`：根据 userId 反查活跃 session；新增 `get_restored_tokens_for_server()`：供 MCP server 启动时填充自己的 LRU；`set_context_token()` 改为写入后自动持久化 |
| `claude_channel/server.py` | 启动时调用 `restore_context_tokens()` + `get_restored_tokens_for_server()` 恢复 tokens；poll_loop 中收到 context_token 时同步调用 `set_context_token()` 持久化 |

---

## Phase 2: contextToken 软失败 + API 请求头增强 + QR IDC 重定向（中优先级）

### 2.1 contextToken 软失败

旧版缺失 contextToken 时直接 `throw Error` 拒绝发送。新版改为 `warn` 并继续尝试发送。

**修改文件:**

| 文件 | 改动说明 |
|---|---|
| `messaging/send.py` | `_require_context_token()` 重命名为 `_warn_missing_context_token()`，从 `raise RuntimeError` 改为 `logger.warning`；所有 4 个 send 函数（text/image/video/file）同步更新 |
| `messaging/error_notice.py` | 无 contextToken 时从 `return`（静默忽略）改为 `warn` 并继续尝试发送 |

### 2.2 API 请求头增强

所有请求新增两个 header，提升协议合规性。

**修改文件:**

| 文件 | 改动说明 |
|---|---|
| `api/client.py` | 新增 `ILINK_APP_ID = "bot"` 和 `ILINK_APP_CLIENT_VERSION`（版本号编码为 uint32: `major<<16 | minor<<8 | patch`）；新增 `_build_common_headers()` 统一管理 `iLink-App-Id`、`iLink-App-ClientVersion`、`SKRouteTag`；`_build_headers` 重命名为 `_build_post_headers`，复用 `_build_common_headers()`；`_api_fetch` 重命名为 `_api_post_fetch`；新增 `api_get_fetch()` 用于 GET 请求（QR 登录使用） |

### 2.3 QR 登录 IDC 重定向

支持扫码后服务端要求切换到不同 IDC host 继续轮询。

**修改文件:**

| 文件 | 改动说明 |
|---|---|
| `auth/login_qr.py` | QR 请求统一用固定地址 `https://ilinkai.weixin.qq.com`（移除对 `api_base_url` 的依赖）；新增扫码状态 `scaned_but_redirect` + `redirect_host` 处理逻辑；`_ActiveLogin` 新增 `current_api_base_url` 字段跟踪当前轮询 host；`_fetch_qr_code` 和 `_poll_qr_status` 改用 `api_get_fetch()`（复用统一 headers）；网络/网关错误（如 Cloudflare 524）不再 throw，降级为 `{"status": "wait"}` 继续轮询；移除了 `httpx` 直接导入和 `_login_client` 共享客户端（改用 `api_get_fetch`）；二维码刷新后打印浏览器链接作为终端渲染失败的兜底 |

---

## Phase 3: 日志敏感字段脱敏 + routeTag 缓存 + 账号清理（低优先级）

### 3.1 日志敏感字段脱敏

**修改文件:**

| 文件 | 改动说明 |
|---|---|
| `util/redact.py` | `redact_body()` 在截断前先将 `context_token`、`bot_token`、`token`、`authorization`、`Authorization` 的 JSON 值替换为 `<redacted>`；新增 `_SENSITIVE_FIELDS_RE` 正则常量 |

### 3.2 routeTag 配置缓存

**修改文件:**

| 文件 | 改动说明 |
|---|---|
| `auth/accounts.py` | `load_config_route_tag()` 结果现在通过 `_load_route_tag_section()` 缓存，避免每次请求都重新读取配置文件 |

### 3.3 账号清理增强

**修改文件:**

| 文件 | 改动说明 |
|---|---|
| `auth/accounts.py` | 新增 `unregister_weixin_account_id()`：从持久化索引中移除 accountId；新增 `clear_stale_accounts_for_user_id()`：QR 登录成功后清理同一 userId 的旧账号，防止 contextToken 歧义；`clear_weixin_account()` 增强：现在清除全部关联文件（`.json` + `.sync.json` + `.context-tokens.json`） |

---

## Vendor 更新

`vendors/openclaw-weixin/` 已从 1.0.2 更新到 2.1.1 作为参考实现。

## 验证

- 65 个测试全部通过
- ruff lint 全部通过
- 15 个文件修改，+435 / -133 行
