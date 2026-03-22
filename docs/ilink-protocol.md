# WeChat ClawBot iLink Bot Protocol

微信 ClawBot 插件底层通信协议（iLink）的技术文档。基于 `@tencent-weixin/openclaw-weixin` v1.0.2 源码分析整理。

## 概述

2026 年 3 月，微信通过 OpenClaw（龙虾）框架正式开放了合法的个人 Bot API。底层协议称为 iLink（智能连接），接入域名为腾讯官方服务器。

架构模型：

```
微信用户 (iOS) → ClawBot 插件 → 腾讯 iLink 服务器 → Bot 程序（HTTP/JSON 长轮询）
```

腾讯定位自己为纯消息管道（pipeline model）：不存储用户输入和 AI 输出，不提供 AI 服务本身。

## 基础信息

| 项目 | 值 |
|------|------|
| 基础 URL | `https://ilinkai.weixin.qq.com` |
| CDN URL | `https://novac2c.cdn.weixin.qq.com/c2c` |
| 协议格式 | HTTP/JSON |
| 认证方式 | Bearer Token（QR 扫码获取） |

## 认证

### 请求头

所有 API 请求携带以下 HTTP 头：

```
Content-Type: application/json
AuthorizationType: ilink_bot_token
Authorization: Bearer {bot_token}
X-WECHAT-UIN: {base64(String(randomUint32()))}
```

- `Authorization`: QR 扫码登录后获取的 bot_token
- `X-WECHAT-UIN`: 每次请求生成新的随机 uint32，转为十进制字符串后 base64 编码。用于防重放攻击
- `AuthorizationType`: 固定值 `ilink_bot_token`

### QR 扫码登录流程

**步骤 1: 获取二维码**

```
GET /ilink/bot/get_bot_qrcode?bot_type=3
```

响应：
```json
{
  "qrcode": "会话标识符",
  "qrcode_img_content": "data:image/png;base64,..."
}
```

`bot_type=3` 为硬编码值，含义未公开文档化。

**步骤 2: 轮询扫码状态**

```
GET /ilink/bot/get_qrcode_status?qrcode={qrcode}
Headers: iLink-App-ClientVersion: 1
```

响应状态值：

| status | 含义 |
|--------|------|
| `wait` | 等待扫码 |
| `scaned` | 已扫码，等待用户确认 |
| `expired` | 二维码过期（需刷新，最多 3 次） |
| `confirmed` | 登录成功 |

登录成功响应：
```json
{
  "status": "confirmed",
  "ilink_bot_id": "xxx@im.bot",
  "bot_token": "Bearer token",
  "baseurl": "https://ilinkai.weixin.qq.com",
  "ilink_user_id": "用户 ID"
}
```

二维码有效期约 5 分钟，过期后可刷新，最多刷新 3 次。

## API 端点

所有端点基于 `{base_url}/ilink/bot/` 前缀。

| 端点 | 方法 | 功能 | 超时 |
|------|------|------|------|
| `getupdates` | POST | 长轮询接收消息 | 35s |
| `sendmessage` | POST | 发送消息 | 15s |
| `getuploadurl` | POST | 获取 CDN 上传地址 | 15s |
| `getconfig` | POST | 获取配置（typing_ticket） | 10s |
| `sendtyping` | POST | 发送输入状态指示 | 10s |
| `get_bot_qrcode` | GET | 获取登录二维码 | 15s |
| `get_qrcode_status` | GET | 轮询扫码状态 | 35s |

每个 POST 请求体都包含 `base_info` 字段：
```json
{
  "base_info": {
    "channel_version": "1.0.2"
  }
}
```

## 消息收发

### getUpdates（长轮询）

服务器挂起连接最长 35 秒，有新消息时立即返回。

请求：
```json
{
  "get_updates_buf": "",
  "base_info": { "channel_version": "1.0.2" }
}
```

响应：
```json
{
  "ret": 0,
  "errcode": null,
  "errmsg": null,
  "msgs": [WeixinMessage, ...],
  "get_updates_buf": "新的同步游标",
  "longpolling_timeout_ms": 35000
}
```

关键机制：
- `get_updates_buf` 是同步游标，首次请求为空字符串，之后必须回传上次响应返回的值
- 不回传或回传旧值会导致重复收到消息
- 客户端应持久化此值，以便重启后恢复
- 无历史消息查询 API，只能通过长轮询获取实时消息

### sendMessage（发送消息）

请求：
```json
{
  "msg": {
    "to_user_id": "user@im.wechat",
    "client_id": "自定义客户端ID",
    "message_type": 2,
    "message_state": 2,
    "context_token": "从 getUpdates 收到的 token",
    "item_list": [
      {
        "type": 1,
        "text_item": { "text": "回复内容" }
      }
    ]
  },
  "base_info": { "channel_version": "1.0.2" }
}
```

响应：HTTP 200 OK（无响应体）

**context_token 是关键字段**：每条收到的消息都带有 context_token，回复时必须回传同一个 token，否则消息无法关联到正确的对话窗口。

## 消息结构

### WeixinMessage

```
seq              int       消息序列号
message_id       int       唯一消息 ID
from_user_id     string    发送者 ID（格式: xxx@im.wechat）
to_user_id       string    接收者 ID（格式: xxx@im.bot）
client_id        string    客户端 ID
create_time_ms   int       创建时间戳（毫秒）
update_time_ms   int       更新时间戳（毫秒）
delete_time_ms   int       删除时间戳（毫秒）
session_id       string    会话 ID
group_id         string    群组 ID（群聊场景）
message_type     int       消息类型（见下方枚举）
message_state    int       消息状态（见下方枚举）
item_list        array     消息内容列表
context_token    string    会话令牌（回复时必须回传）
```

### 枚举值

**MessageType（消息方向）**：

| 值 | 含义 |
|----|------|
| 0 | NONE |
| 1 | USER（用户发送的消息） |
| 2 | BOT（机器人发送的消息） |

**MessageState（消息状态）**：

| 值 | 含义 |
|----|------|
| 0 | NEW（新消息） |
| 1 | GENERATING（生成中，流式输出） |
| 2 | FINISH（完成） |

**MessageItemType（内容类型）**：

| 值 | 含义 |
|----|------|
| 0 | NONE |
| 1 | TEXT（文本） |
| 2 | IMAGE（图片） |
| 3 | VOICE（语音） |
| 4 | FILE（文件） |
| 5 | VIDEO（视频） |

### MessageItem

```
type          int           内容类型（MessageItemType）
create_time_ms int          创建时间
update_time_ms int          更新时间
is_completed  bool          是否完成
msg_id        string        消息 ID
ref_msg       RefMessage    引用的消息（回复场景）
text_item     TextItem      type=1 时
image_item    ImageItem     type=2 时
voice_item    VoiceItem     type=3 时
file_item     FileItem      type=4 时
video_item    VideoItem     type=5 时
```

### 各类型详细结构

**TextItem**：
```
text    string    文本内容
```

**ImageItem**：
```
media          CDNMedia    原图 CDN 引用
thumb_media    CDNMedia    缩略图 CDN 引用
aeskey         string      hex 格式 AES 密钥
url            string      直接 URL（部分场景）
mid_size       int         中等尺寸大小
thumb_size     int         缩略图大小
thumb_height   int         缩略图高度
thumb_width    int         缩略图宽度
hd_size        int         高清尺寸大小
```

**VoiceItem**：
```
media          CDNMedia    语音 CDN 引用
encode_type    int         编码类型（SILK）
bits_per_sample int        采样位数
sample_rate    int         采样率
playtime       int         播放时长（毫秒）
text           string      微信服务端语音识别结果（可能为空）
```

语音识别说明：微信服务器会自动对语音消息做语音识别，结果存在 `text` 字段。有转写结果时可直接作为文本使用；无转写时需下载音频文件（SILK 格式）自行处理。

**FileItem**：
```
media       CDNMedia    文件 CDN 引用
file_name   string      文件名
md5         string      明文 MD5
len         string      文件大小（字节）
```

**VideoItem**：
```
media          CDNMedia    视频 CDN 引用
thumb_media    CDNMedia    缩略图 CDN 引用
video_size     int         视频大小
play_length    int         播放时长（毫秒）
video_md5      string      明文 MD5
thumb_size     int         缩略图大小
thumb_height   int         缩略图高度
thumb_width    int         缩略图宽度
```

**CDNMedia（所有媒体类型共用）**：
```
encrypt_query_param   string    CDN 下载/上传参数
aes_key               string    base64 编码的 AES-128 密钥
encrypt_type          int       加密方式（0=fileid, 1=packed）
```

**RefMessage（引用消息）**：
```
message_item   MessageItem    被引用的消息内容
title          string         引用标题
```

## CDN 媒体协议

所有媒体文件通过腾讯 CDN 传输，使用 AES-128-ECB 加密。

### 上传流程

**步骤 1: 获取上传地址**

```json
POST /ilink/bot/getuploadurl
{
  "filekey": "16字节随机hex",
  "media_type": 1,
  "to_user_id": "目标用户ID",
  "rawsize": 原文件字节数,
  "rawfilemd5": "明文MD5",
  "filesize": AES加密后字节数,
  "no_need_thumb": true,
  "aeskey": "16字节AES密钥的hex表示",
  "base_info": { "channel_version": "1.0.2" }
}
```

UploadMediaType 枚举：

| 值 | 类型 |
|----|------|
| 1 | IMAGE |
| 2 | VIDEO |
| 3 | FILE |
| 4 | VOICE |

响应：
```json
{
  "upload_param": "加密的上传参数",
  "thumb_upload_param": "缩略图上传参数（如需要）"
}
```

**步骤 2: AES-128-ECB 加密**

- 算法：AES-128-ECB
- 填充：PKCS7
- 密钥：随机生成的 16 字节
- 加密后大小计算：`ceil((plaintext_size + 1) / 16) * 16`

**步骤 3: 上传到 CDN**

```
POST {cdn_base_url}/upload?encrypted_query_param={upload_param}&filekey={filekey}
Content-Type: application/octet-stream
Body: <加密后的二进制数据>
```

成功响应头：
- `x-encrypted-param`: 下载参数（必须保存，用于后续下载引用）

错误响应头：
- `x-error-message`: 错误信息

上传重试策略：最多 3 次，4xx 错误立即失败，5xx 错误重试。

**步骤 4: 在 sendMessage 中引用**

上传完成后，在 sendMessage 的 item_list 中使用 CDNMedia 结构引用已上传的文件。

### 下载流程

**步骤 1: 构建下载 URL**

```
{cdn_base_url}/download?encrypted_query_param={encrypt_query_param}
```

**步骤 2: 下载并解密**

1. HTTP GET 下载密文
2. 解析 AES 密钥（两种编码兼容）：
   - 直接 16 字节: `base64decode(aes_key)` 得到 16 字节
   - hex 字符串: `base64decode(aes_key)` 得到 32 字符 hex，再 `bytes.fromhex()` 得到 16 字节
3. AES-128-ECB 解密
4. PKCS7 去填充
5. 得到明文文件

## Typing 指示器（正在输入）

### 获取 typing_ticket

```json
POST /ilink/bot/getconfig
{
  "ilink_user_id": "用户ID",
  "context_token": "可选",
  "base_info": { "channel_version": "1.0.2" }
}
```

响应：
```json
{
  "ret": 0,
  "errmsg": null,
  "typing_ticket": "base64编码的ticket"
}
```

typing_ticket 按用户获取，建议缓存（TTL 24 小时），失败时指数退避重试（最长 1 小时）。

### 发送输入状态

```json
POST /ilink/bot/sendtyping
{
  "ilink_user_id": "用户ID",
  "typing_ticket": "从 getConfig 获取",
  "status": 1,
  "base_info": { "channel_version": "1.0.2" }
}
```

**TypingStatus 枚举**：

| 值 | 含义 |
|----|------|
| 1 | TYPING（正在输入） |
| 2 | CANCEL（取消输入） |

使用模式：
1. 开始处理时发送 `status=1`
2. 每 5 秒发送一次 keepalive（重复 `status=1`）
3. 回复完成后发送 `status=2` 取消

## 错误处理

### 错误码

| 错误码 | 含义 | 处理策略 |
|--------|------|----------|
| `ret=0` | 成功 | - |
| `errcode=-14` | 会话超时 | 暂停该账户所有 API 调用 1 小时 |
| HTTP 4xx | 客户端错误 | 检查请求参数 |
| HTTP 5xx | 服务端错误 | 重试 |

### 重试策略（实现建议）

- 长轮询连续失败：1-2 次等待 2 秒，3 次以上等待 30 秒
- CDN 上传：最多重试 3 次
- getConfig 失败：指数退避，最长 1 小时
- 会话超时（errcode=-14）：暂停 1 小时后恢复

## 群聊支持

WeixinMessage 包含 `group_id` 字段，表明协议原生支持群聊场景。群聊消息的 `group_id` 非空，`from_user_id` 为发送者个人 ID。具体权限要求未公开文档化。

## 已知限制

- 无历史消息查询 API
- 速率限制未公开披露
- bot_type 参数含义未文档化
- 需要 OpenClaw 平台生态
- 腾讯保留单方面变更、中断或终止服务的权利
- Bot 发送的消息中链接不可点击（纯文本展示）

## 用户协议要点

基于微信 ClawBot 插件服务条款：

- **管道模型**：腾讯仅提供消息收发通道，不存储输入/输出内容，不提供 AI 服务
- **数据收集**：IP 地址、操作日志、设备信息用于安全审计
- **控制保留**：腾讯可控制支持的客户端类型、可连接 AI 服务范围、通信规模/频率
- **内容审查**：可通过过滤、拦截等方式识别和处理内容
- **服务终止**：腾讯可根据业务需要单方面变更、中断或终止服务

## 参考

- TS 原版实现：`@tencent-weixin/openclaw-weixin` v1.0.2（npm）
- Python 移植：[wechat-clawbot](https://github.com/nightsailer/wechat-clawbot)
- 逆向分析参考：[hao-ji-xing/openclaw-weixin](https://github.com/hao-ji-xing/openclaw-weixin)
- OpenClaw 文档：https://docs.openclaw.ai
