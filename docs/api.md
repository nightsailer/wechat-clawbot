# wechat-clawbot API Reference

## `wechat_clawbot.api.types` — Protocol Types

All data structures mirror the WeChat ilink protobuf API. Fields use JSON-over-HTTP encoding (bytes as base64 strings).

### Enums

| Enum | Values |
|------|--------|
| `UploadMediaType` | `IMAGE=1`, `VIDEO=2`, `FILE=3`, `VOICE=4` |
| `MessageType` | `NONE=0`, `USER=1`, `BOT=2` |
| `MessageItemType` | `NONE=0`, `TEXT=1`, `IMAGE=2`, `VOICE=3`, `FILE=4`, `VIDEO=5` |
| `MessageState` | `NEW=0`, `GENERATING=1`, `FINISH=2` |
| `TypingStatus` | `TYPING=1`, `CANCEL=2` |

### Dataclasses

#### `WeixinMessage`

```python
@dataclass
class WeixinMessage:
    seq: int | None
    message_id: int | None
    from_user_id: str | None
    to_user_id: str | None
    client_id: str | None
    create_time_ms: int | None
    update_time_ms: int | None         # v0.4.0+
    delete_time_ms: int | None         # v0.4.0+
    session_id: str | None
    group_id: str | None               # v0.4.0+
    message_type: int | None           # MessageType
    message_state: int | None          # MessageState
    item_list: list[MessageItem] | None
    context_token: str | None          # echo in replies to maintain session
```

#### `MessageItem`

```python
@dataclass
class MessageItem:
    type: int | None               # MessageItemType
    create_time_ms: int | None     # v0.4.0+
    update_time_ms: int | None     # v0.4.0+
    is_completed: bool | None      # v0.4.0+
    msg_id: str | None             # v0.4.0+
    ref_msg: RefMessage | None     # quoted message
    text_item: TextItem | None
    image_item: ImageItem | None
    voice_item: VoiceItem | None
    file_item: FileItem | None
    video_item: VideoItem | None
```

#### `CDNMedia`

```python
@dataclass
class CDNMedia:
    encrypt_query_param: str | None   # download parameter
    aes_key: str | None               # base64-encoded AES key
    encrypt_type: int | None          # 0=fileid, 1=packed
    full_url: str | None              # server-provided direct download URL (v0.3.0+)

    @property
    def has_download_source(self) -> bool   # True if encrypt_query_param or full_url is set
```

#### Request/Response types

- `GetUpdatesReq(get_updates_buf)` / `GetUpdatesResp(ret, errcode, errmsg, msgs, get_updates_buf, longpolling_timeout_ms)`
- `GetUploadUrlReq(filekey, media_type, to_user_id, rawsize, rawfilemd5, filesize, ...)` / `GetUploadUrlResp(upload_param, thumb_upload_param, upload_full_url)`
- `SendMessageReq(msg: WeixinMessage)`
- `SendTypingReq(ilink_user_id, typing_ticket, status)` / `GetConfigResp(ret, errmsg, typing_ticket)`

### Parsing helpers

```python
def dict_to_weixin_message(d: dict) -> WeixinMessage
def dict_to_get_updates_resp(d: dict) -> GetUpdatesResp
```

---

## `wechat_clawbot.api.client` — HTTP API Client

All functions are `async`. Uses a shared `httpx.AsyncClient` for connection pooling.

All requests include `iLink-App-Id` and `iLink-App-ClientVersion` headers (v0.3.0+).

### `ApiHttpError`

```python
class ApiHttpError(RuntimeError):
    status_code: int   # HTTP status code for structured error handling
```

Raised by `api_get_fetch` and `_api_post_fetch` on HTTP 4xx/5xx responses.

### `WeixinApiOptions`

```python
@dataclass
class WeixinApiOptions:
    base_url: str                       # e.g. "https://ilinkai.weixin.qq.com"
    token: str | None = None            # Bearer token from QR login
    timeout_ms: int | None = None
    context_token: str | None = None    # for send operations
```

### Functions

#### `get_updates`

```python
async def get_updates(
    base_url: str,
    token: str | None = None,
    get_updates_buf: str = "",
    timeout_ms: int | None = None,      # default: 35_000
) -> GetUpdatesResp
```

Long-poll for new messages. Returns empty response (no error) on client-side timeout.

#### `send_message`

```python
async def send_message(opts: WeixinApiOptions, body: SendMessageReq) -> None
```

#### `get_upload_url`

```python
async def get_upload_url(req: GetUploadUrlReq, opts: WeixinApiOptions) -> GetUploadUrlResp
```

Get a pre-signed CDN upload URL.

#### `get_config`

```python
async def get_config(
    opts: WeixinApiOptions,
    ilink_user_id: str,
    context_token: str | None = None,
) -> GetConfigResp
```

Fetch bot config including `typing_ticket`.

#### `send_typing`

```python
async def send_typing(opts: WeixinApiOptions, body: SendTypingReq) -> None
```

#### `api_get_fetch`

```python
async def api_get_fetch(
    base_url: str,
    endpoint: str,
    timeout_ms: int,
    label: str,
) -> str
```

GET request wrapper with common iLink headers. Raises `ApiHttpError` on HTTP errors.

#### `close_shared_client`

```python
async def close_shared_client() -> None
```

Close the shared httpx client. Call during application shutdown.

---

## `wechat_clawbot.api.poll_core` — Shared Poll Loop *(v0.4.0+)*

Reusable `getUpdates` poll loop with retry, back-off, session-guard, and sync-buf persistence. Used by the gateway poller.

```python
MAX_CONSECUTIVE_FAILURES = 3
FAILURE_RETRY_DELAY = 2.0
FAILURE_BACKOFF_DELAY = 30.0
SESSION_PAUSE_POLL_DELAY = 60.0

MessageProcessor = Callable[[GetUpdatesResp], Awaitable[None]]

async def poll_loop(
    *,
    account_id: str,
    base_url: str,
    token: str | None,
    sync_buf_path: Path,
    on_response: MessageProcessor,
    stop_event: anyio.Event,
) -> None
```

Runs until `stop_event` is set. Handles session expiration (via `session_guard`) and exponential back-off on repeated failures.

---

## `wechat_clawbot.api.session_guard` — Session Expiration

```python
SESSION_EXPIRED_ERRCODE = -14

def pause_session(account_id: str) -> None
def is_session_paused(account_id: str) -> bool
def get_remaining_pause_ms(account_id: str) -> int
def assert_session_active(account_id: str) -> None   # raises RuntimeError if paused
```

---

## `wechat_clawbot.api.config_cache` — Config Cache

```python
@dataclass
class CachedConfig:
    typing_ticket: str = ""

class WeixinConfigManager:
    def __init__(self, api_opts: WeixinApiOptions, log: Callable[[str], None]) -> None: ...
    async def get_for_user(self, user_id: str, context_token: str | None = None) -> CachedConfig: ...
```

24-hour TTL with exponential-backoff retry on failure (up to 1 hour).

---

## `wechat_clawbot.auth.accounts` — Account Management

### Constants

```python
DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"
CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"
```

### Account ID utilities

```python
def normalize_account_id(raw: str) -> str                  # "hex@im.bot" -> "hex-im-bot"
def derive_raw_account_id(normalized_id: str) -> str | None # reverse
```

### Account CRUD

```python
def list_indexed_weixin_account_ids() -> list[str]
def register_weixin_account_id(account_id: str) -> None
def load_weixin_account(account_id: str) -> WeixinAccountData | None
def save_weixin_account(account_id: str, *, token=None, base_url=None, user_id=None) -> None
def clear_weixin_account(account_id: str) -> None           # removes .json + .sync.json + .context-tokens.json
def unregister_weixin_account_id(account_id: str) -> None   # remove from persistent index
def clear_stale_accounts_for_user_id(                       # cleanup stale accounts after re-login
    current_account_id: str, user_id: str,
    on_clear_context_tokens: Callable[[str], None] | None = None,
) -> None
```

### Account resolution

```python
class ResolvedWeixinAccount:
    account_id: str
    base_url: str
    cdn_base_url: str
    token: str | None
    enabled: bool
    configured: bool       # True when token exists
    name: str | None

def resolve_weixin_account(cfg: dict | None, account_id: str | None) -> ResolvedWeixinAccount
def list_weixin_account_ids() -> list[str]
```

### Config

```python
def load_config_route_tag(account_id: str | None = None) -> str | None
```

---

## `wechat_clawbot.auth.login_qr` — QR Code Login

```python
DEFAULT_ILINK_BOT_TYPE = "3"

class WeixinQrStartResult:
    qrcode_url: str | None
    message: str
    session_key: str

class WeixinQrWaitResult:
    connected: bool
    bot_token: str | None
    account_id: str | None
    base_url: str | None
    user_id: str | None
    message: str

async def start_weixin_login_with_qr(
    api_base_url: str,
    bot_type: str = "3",
    account_id: str | None = None,
    force: bool = False,
) -> WeixinQrStartResult

async def wait_for_weixin_login(
    session_key: str,
    api_base_url: str,
    bot_type: str = "3",
    timeout_ms: int | None = None,    # default: 480_000
    verbose: bool = False,
) -> WeixinQrWaitResult
```

---

## `wechat_clawbot.auth.pairing` — Framework Authorization

```python
def resolve_framework_allow_from_path(account_id: str) -> Path
def read_framework_allow_from_list(account_id: str) -> list[str]
async def register_user_in_framework_store(account_id: str, user_id: str) -> bool
```

---

## `wechat_clawbot.cdn.aes_ecb` — AES-128-ECB Crypto

```python
def encrypt_aes_ecb(plaintext: bytes, key: bytes) -> bytes
def decrypt_aes_ecb(ciphertext: bytes, key: bytes) -> bytes
def aes_ecb_padded_size(plaintext_size: int) -> int
```

---

## `wechat_clawbot.cdn.cdn_url` — CDN URL Builders

```python
ENABLE_CDN_URL_FALLBACK = True   # When False, full_url is required (no client-side URL construction)

def build_cdn_download_url(encrypted_query_param: str, cdn_base_url: str) -> str
def build_cdn_upload_url(cdn_base_url: str, upload_param: str, filekey: str) -> str
```

---

## `wechat_clawbot.cdn.download` — CDN Download + Decrypt

```python
async def download_and_decrypt_buffer(
    encrypted_query_param: str,
    aes_key_base64: str,
    cdn_base_url: str,
    label: str,
    full_url: str | None = None,    # preferred over encrypt_query_param when set
) -> bytes

async def download_plain_cdn_buffer(
    encrypted_query_param: str,
    cdn_base_url: str,
    label: str,
    full_url: str | None = None,    # preferred over encrypt_query_param when set
) -> bytes

async def close_cdn_dl_client() -> None
```

URL resolution priority: `full_url` > `build_cdn_download_url(encrypt_query_param)` > error (when `ENABLE_CDN_URL_FALLBACK=False`).

---

## `wechat_clawbot.cdn.upload` — CDN Upload Pipeline

```python
@dataclass
class UploadedFileInfo:
    filekey: str
    download_encrypted_query_param: str
    aeskey: str                      # hex-encoded
    file_size: int                   # plaintext bytes
    file_size_ciphertext: int        # encrypted bytes

async def download_remote_image_to_temp(url: str, dest_dir: str) -> str

async def upload_file_to_weixin(
    file_path: str, to_user_id: str, opts: WeixinApiOptions, cdn_base_url: str
) -> UploadedFileInfo

async def upload_video_to_weixin(
    file_path: str, to_user_id: str, opts: WeixinApiOptions, cdn_base_url: str
) -> UploadedFileInfo

async def upload_file_attachment_to_weixin(
    file_path: str, to_user_id: str, opts: WeixinApiOptions, cdn_base_url: str
) -> UploadedFileInfo

async def close_cdn_ul_client() -> None
```

---

## `wechat_clawbot.media.mime` — MIME Types

```python
EXTENSION_TO_MIME: dict[str, str]    # ".jpg" -> "image/jpeg"
MIME_TO_EXTENSION: dict[str, str]    # "image/jpeg" -> ".jpg"

def get_mime_from_filename(filename: str) -> str
def get_extension_from_mime(mime_type: str) -> str
def get_extension_from_content_type_or_url(content_type: str | None, url: str) -> str
```

---

## `wechat_clawbot.media.download` — Media Download

```python
SaveMediaFn = Callable[..., Awaitable[dict[str, str]]]

class InboundMediaOpts:
    decrypted_pic_path: str | None
    decrypted_voice_path: str | None
    voice_media_type: str | None
    decrypted_file_path: str | None
    file_media_type: str | None
    decrypted_video_path: str | None

async def download_media_from_item(
    item: MessageItem,
    cdn_base_url: str,
    save_media: SaveMediaFn,
    log: Callable[[str], None],
    err_log: Callable[[str], None],
    label: str,
) -> InboundMediaOpts
```

---

## `wechat_clawbot.media.silk` — SILK Transcoding

```python
async def silk_to_wav(silk_buf: bytes) -> bytes | None
```

Returns WAV bytes, or `None` if `graiax-silkcoder` is not installed. Install with `pip install "wechat-clawbot[silk]"`.

---

## `wechat_clawbot.messaging.mcp_defs` — Shared MCP Definitions *(v0.4.0+)*

Shared tool schemas and instructions used by both the gateway MCP channel and the standalone `claude_channel` server.

```python
INSTRUCTIONS: str   # System instructions for MCP clients

TOOLS: list[MCPTool]
# Contains: wechat_reply, wechat_send_file, wechat_typing

def build_channel_notification(sender_id: str, text: str) -> JSONRPCNotification
```

### MCP Tool: `wechat_reply`

```json
{
  "name": "wechat_reply",
  "inputSchema": {
    "type": "object",
    "properties": {
      "sender_id": { "type": "string", "description": "xxx@im.wechat format" },
      "text": { "type": "string", "description": "plain text, no markdown" }
    },
    "required": ["sender_id", "text"]
  }
}
```

### MCP Tool: `wechat_send_file`

```json
{
  "name": "wechat_send_file",
  "inputSchema": {
    "type": "object",
    "properties": {
      "sender_id": { "type": "string", "description": "xxx@im.wechat format" },
      "file_path": { "type": "string", "description": "Absolute path to the local file" },
      "text": { "type": "string", "description": "Optional caption text", "default": "" }
    },
    "required": ["sender_id", "file_path"]
  }
}
```

### MCP Tool: `wechat_typing`

```json
{
  "name": "wechat_typing",
  "inputSchema": {
    "type": "object",
    "properties": {
      "sender_id": { "type": "string", "description": "xxx@im.wechat format" }
    },
    "required": ["sender_id"]
  }
}
```

---

## `wechat_clawbot.messaging.inbound` — Inbound Messages

```python
@dataclass
class WeixinMsgContext:
    body: str
    from_user: str
    to: str
    account_id: str
    originating_channel: str       # "openclaw-weixin"
    originating_to: str            # v0.4.0+
    message_sid: str
    timestamp: int | None
    provider: str                  # "openclaw-weixin"
    chat_type: str                 # "direct"
    session_key: str | None        # v0.4.0+
    context_token: str | None
    media_url: str | None          # v0.4.0+
    media_path: str | None
    media_type: str | None
    command_body: str | None
    command_authorized: bool | None

def set_context_token(account_id: str, user_id: str, token: str) -> None  # persists to disk, skips if unchanged
def get_context_token(account_id: str, user_id: str) -> str | None
def restore_context_tokens(account_id: str) -> None                       # restore from disk on startup
def clear_context_tokens_for_account(account_id: str) -> None             # clear memory + disk
def find_account_ids_by_context_token(account_ids: list[str], user_id: str) -> list[str]
def get_restored_tokens_for_server(account_id: str) -> dict[str, str]     # {user_id: token}
def is_media_item(item: MessageItem) -> bool
def body_from_item_list(item_list: list[MessageItem] | None) -> str
def weixin_message_to_msg_context(
    msg: WeixinMessage, account_id: str, opts: InboundMediaOpts | None = None
) -> WeixinMsgContext
```

---

## `wechat_clawbot.messaging.send` — Send Messages

```python
def markdown_to_plain_text(text: str) -> str

async def send_message_weixin(to: str, text: str, opts: WeixinApiOptions) -> dict[str, str]
async def send_image_message_weixin(to: str, text: str, uploaded: UploadedFileInfo, opts: WeixinApiOptions) -> dict[str, str]
async def send_video_message_weixin(to: str, text: str, uploaded: UploadedFileInfo, opts: WeixinApiOptions) -> dict[str, str]
async def send_file_message_weixin(to: str, text: str, file_name: str, uploaded: UploadedFileInfo, opts: WeixinApiOptions) -> dict[str, str]
```

All send functions warn (but proceed) if `opts.context_token` is absent — the server accepts messages without it since iLink v2.1+, though they may not associate with the correct conversation. Returns `{"messageId": "..."}`.

---

## `wechat_clawbot.messaging.send_media` — Send Media Files

```python
async def send_weixin_media_file(
    file_path: str,
    to: str,
    text: str,
    opts: WeixinApiOptions,
    cdn_base_url: str,
) -> dict[str, str]
```

Routes by MIME type: `video/*` -> video, `image/*` -> image, else -> file attachment.

---

## `wechat_clawbot.messaging.slash_commands` — Slash Commands

```python
@dataclass
class SlashCommandResult:
    handled: bool

@dataclass
class SlashCommandContext:
    to: str
    context_token: str | None
    base_url: str
    token: str | None
    account_id: str
    log: Callable[[str], None]
    err_log: Callable[[str], None]

async def handle_slash_command(
    content: str,
    ctx: SlashCommandContext,
    received_at: float,
    event_timestamp: int | None = None,
) -> SlashCommandResult
```

Built-in commands: `/echo <message>`, `/toggle-debug`.

---

## `wechat_clawbot.messaging.debug_mode`

```python
def toggle_debug_mode(account_id: str) -> bool
def is_debug_mode(account_id: str) -> bool
```

---

## `wechat_clawbot.messaging.error_notice`

```python
async def send_weixin_error_notice(
    to: str,
    context_token: str | None,
    message: str,
    base_url: str,
    token: str | None,
    err_log: Callable[[str], None],
) -> None
```

Fire-and-forget. Warns but still attempts to send when `context_token` is absent.

---

## `wechat_clawbot.messaging.process_message` — Message Pipeline

```python
class ReplyDispatcher(Protocol):
    async def dispatch(self, text: str, media_url: str | None = None) -> None: ...

@dataclass
class ProcessMessageDeps:
    account_id: str
    config: dict[str, Any]
    base_url: str
    cdn_base_url: str
    token: str | None = None
    typing_ticket: str | None = None
    log: Callable[[str], None]
    err_log: Callable[[str], None]
    save_media: SaveMediaFn | None = None
    dispatch_reply: Callable[..., Awaitable[None]] | None = None

async def process_one_message(full: WeixinMessage, deps: ProcessMessageDeps) -> None
```

---

## `wechat_clawbot.monitor.monitor` — Long-Poll Loop

```python
@dataclass
class MonitorOpts:
    base_url: str
    cdn_base_url: str
    token: str | None = None
    account_id: str = ""
    config: dict[str, Any] | None = None
    log: Callable[[str], None]
    err_log: Callable[[str], None]
    long_poll_timeout_ms: int | None = None
    set_status: Callable[[dict], None] | None = None
    save_media: Callable[..., Awaitable[dict[str, str]]] | None = None
    dispatch_reply: Callable[..., Awaitable[None]] | None = None

async def monitor_weixin_provider(
    opts: MonitorOpts,
    stop_event: asyncio.Event | None = None,
) -> None
```

Runs until `stop_event` is set. Handles retries (3 failures -> 30s backoff) and session expiration (1h pause).

---

## `wechat_clawbot.config.schema` — Configuration

```python
class WeixinAccountConfig(BaseModel):
    name: str | None
    enabled: bool | None
    base_url: str          # alias: baseUrl, default: DEFAULT_BASE_URL
    cdn_base_url: str      # alias: cdnBaseUrl, default: CDN_BASE_URL
    route_tag: int | None  # alias: routeTag

class WeixinConfigSchema(BaseModel):
    # inherits all WeixinAccountConfig fields, plus:
    accounts: dict[str, WeixinAccountConfig] | None
```

---

## `wechat_clawbot.storage.state_dir`

```python
def resolve_state_dir() -> Path
```

Precedence: `$OPENCLAW_STATE_DIR` > `$CLAWDBOT_STATE_DIR` > `~/.openclaw`.

---

## `wechat_clawbot.storage.sync_buf`

```python
def get_sync_buf_file_path(account_id: str) -> Path
def load_get_updates_buf(file_path: Path) -> str | None
def save_get_updates_buf(file_path: Path, get_updates_buf: str) -> None
```

---

## `wechat_clawbot.util.logger`

```python
logger = Logger()                          # module-level singleton

class Logger:
    def info(self, message: str) -> None
    def debug(self, message: str) -> None
    def warning(self, message: str) -> None
    def error(self, message: str) -> None
    def with_account(self, account_id: str) -> Logger
    def get_log_file_path(self) -> str

def set_log_level(level: str) -> None      # "DEBUG", "INFO", "WARN", "ERROR"
```

Writes JSON lines to `/tmp/openclaw/openclaw-YYYY-MM-DD.log`.

---

## `wechat_clawbot.util.random`

```python
def generate_id(prefix: str) -> str              # "prefix:1234567890-abcdef01"
def temp_file_name(prefix: str, ext: str) -> str  # "prefix-1234567890-abcdef01.jpg"
```

---

## `wechat_clawbot.util.redact`

```python
def truncate(s: str | None, max_len: int) -> str
def redact_token(token: str | None, prefix_len: int = 6) -> str
def redact_body(body: str | None, max_len: int = 200) -> str   # redacts context_token/bot_token/token/authorization before truncating
def redact_url(raw_url: str) -> str
```

---

## `wechat_clawbot.util.fs` — Filesystem Utilities *(v0.4.0+)*

```python
def atomic_write_text(path: Path, text: str) -> None
```

Write text to `path` atomically using a temp file + `os.replace`. Creates parent directories as needed.

---

## `wechat_clawbot.claude_channel` — Claude Code Channel Bridge

### CLI (`wechat-clawbot-cc`)

```bash
wechat-clawbot-cc setup    # Interactive QR login
wechat-clawbot-cc serve    # Start MCP channel server (direct mode)
wechat-clawbot-cc serve --gateway <url> --endpoint <id>  # Bridge mode (v0.4.0+)
wechat-clawbot-cc serve --gateway <url> --endpoint <id> --api-key <key>  # With auth
wechat-clawbot-cc help     # Show help
```

**Direct mode** polls WeChat directly using saved credentials. **Bridge mode** *(v0.4.0+)* connects to a gateway SSE endpoint, forwarding tool calls via the gateway API.

### `claude_channel.credentials`

```python
@dataclass
class AccountData:
    token: str
    base_url: str
    account_id: str
    user_id: str | None = None
    saved_at: str | None = None

def credentials_dir() -> Path               # ~/.claude/channels/wechat/
def credentials_file_path() -> Path          # ~/.claude/channels/wechat/account.json
def load_credentials() -> AccountData | None
def save_credentials(data: AccountData) -> None
```

### `claude_channel.setup`

```python
async def do_qr_login(base_url: str = DEFAULT_BASE_URL) -> AccountData | None
```

### `claude_channel.server`

```python
async def run_channel_server(account: AccountData) -> None
```

Starts the MCP server on stdio, registers the `wechat_reply`, `wechat_send_file`, and `wechat_typing` tools, and begins long-polling for WeChat messages. Tool definitions are imported from `messaging.mcp_defs`.

### `claude_channel.bridge` *(v0.4.0+)*

```python
async def run_bridge_server(gateway_url: str, endpoint_id: str, api_key: str = "") -> None
```

Starts a bridge MCP server that connects to a gateway SSE endpoint instead of polling WeChat directly. Supports both Claude Code (channel notifications) and Codex (resource notifications + `wechat_get_messages` polling tool).

Additional tools in bridge mode:

- `wechat_get_messages` — drain pending messages from the queue (for non-channel clients)
- `wechat://messages/pending` — MCP resource for pending message count

---

## `wechat_clawbot.gateway` — Multi-Bot, Multi-Endpoint Routing Gateway *(v0.4.0+)*

The gateway routes messages from multiple WeChat Bot accounts (downstream) to multiple upstream AI endpoints. Requires the `gateway` extra: `pip install wechat-clawbot[gateway]`.

### `gateway.types` — Core Data Types

#### Enums

| Enum | Values |
|------|--------|
| `ChannelType` | `MCP="mcp"`, `SDK="sdk"`, `HTTP="http"` |
| `EndpointStatus` | `ONLINE="online"`, `OFFLINE="offline"`, `ERROR="error"` |
| `DeliveryStatus` | `PENDING="pending"`, `DELIVERED="delivered"`, `EXPIRED="expired"` |
| `UserRole` | `ADMIN="admin"`, `USER="user"`, `GUEST="guest"` |
| `RouteType` | `ACTIVE_ENDPOINT="active-endpoint"`, `MENTION="mention"`, `COMMAND_TO="command-to"`, `GATEWAY_COMMAND="gateway-command"` |

#### Dataclasses

```python
@dataclass
class EndpointConfig:
    id: str
    name: str
    type: ChannelType
    url: str = ""
    tags: list[str] = field(default_factory=list)
    api_key: str = ""
    description: str = ""

@dataclass
class AccountConfig:
    id: str
    credentials_path: str = ""
    token: str = ""
    base_url: str = "https://ilinkai.weixin.qq.com"

@dataclass
class UserState:
    user_id: str
    display_name: str = ""
    role: UserRole = UserRole.GUEST
    active_endpoint: str = ""
    bindings: list[EndpointBinding] = field(default_factory=list)
    endpoint_sessions: dict[str, EndpointSession] = field(default_factory=dict)
    account_id: str = ""
    created_at: float
    last_active_at: float

    def is_bound_to(self, endpoint_id: str) -> bool
    def get_binding(self, endpoint_id: str) -> EndpointBinding | None

@dataclass
class EndpointInfo:
    config: EndpointConfig
    status: EndpointStatus = EndpointStatus.OFFLINE
    connected_at: float = 0.0
    last_active_at: float = 0.0
    error_message: str = ""

@dataclass
class InboundMessage:
    account_id: str
    sender_id: str
    text: str
    context_token: str | None = None
    message_id: str = ""
    timestamp: float = 0.0
    media_path: str = ""
    media_type: str = ""

@dataclass
class RouteResult:
    type: RouteType
    endpoint_id: str = ""
    cleaned_text: str = ""
    command: str = ""
    command_args: str = ""
    error: str = ""

@dataclass
class DeliveryRecord:
    id: int = 0
    message_id: str = ""
    account_id: str = ""
    sender_id: str = ""
    endpoint_id: str = ""
    content: str = ""
    context_token: str | None = None
    status: DeliveryStatus = DeliveryStatus.PENDING
    created_at: float = 0.0
    delivered_at: float = 0.0
    retry_count: int = 0
    next_retry_at: float = 0.0
```

### `gateway.config` — Configuration

```python
DEFAULT_STATE_DIR = Path.home() / ".clawbot-gateway"
DEFAULT_CONFIG_NAME = "gateway.yaml"
ENV_CONFIG_PATH = "CLAWBOT_GATEWAY_CONFIG"

class GatewayServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8765
    admin_port: int = 8766
    admin_token: str = ""
    log_level: str = "info"

class AccountConfigModel(BaseModel):
    credentials: str | None = None
    token: str | None = None
    base_url: str = "https://ilinkai.weixin.qq.com"

class EndpointConfigModel(BaseModel):
    name: str = ""
    type: ChannelType = ChannelType.MCP
    url: str = ""
    tags: list[str] = Field(default_factory=list)
    api_key: str = ""
    description: str = ""

class RoutingConfig(BaseModel):
    strategy: Literal["active-endpoint", "prefix", "smart"] = "active-endpoint"
    mention_prefix: str = "@"
    gateway_commands: list[str] = Field(default_factory=lambda: ["/"])

class AuthorizationConfig(BaseModel):
    mode: Literal["allowlist", "open", "invite-code"] = "allowlist"
    default_endpoints: list[str] = Field(default_factory=list)
    admins: list[str] = Field(default_factory=list)

class ArchiveConfig(BaseModel):
    enabled: bool = False
    storage: str = "sqlite"
    path: str = ""
    retention_days: int = 0

class GatewayConfig(BaseModel):
    gateway: GatewayServerConfig
    accounts: dict[str, AccountConfigModel]
    endpoints: dict[str, EndpointConfigModel]
    routing: RoutingConfig
    authorization: AuthorizationConfig
    archive: ArchiveConfig

def resolve_gateway_state_dir() -> Path
def load_gateway_config(config_path: Path | None = None) -> GatewayConfig
def scaffold_gateway_config(state_dir: Path) -> Path
```

Config file resolution order: explicit `config_path` > `$CLAWBOT_GATEWAY_CONFIG` env > `~/.clawbot-gateway/gateway.yaml`.

### `gateway.db` — Async SQLite Base Class

```python
class AsyncSQLiteStore:
    def __init__(self, db_path: Path) -> None
    def _get_schema_sql(self) -> str          # subclasses must override
    async def open(self) -> None              # creates DB, enables WAL mode, runs schema
    async def close(self) -> None
    async def _run(self, fn: Callable[[], Any]) -> Any   # run in worker thread with capacity limiter
```

Base class for `DeliveryQueue` and `MessageArchive`. Uses WAL mode and `anyio.to_thread.run_sync` with a capacity limiter for thread-safe access.

### `gateway.admin` — Admin HTTP API

Protected by Bearer-token authentication when `admin_token` is configured.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/status` | Overall gateway status |
| `GET` | `/api/accounts` | List configured Bot accounts |
| `GET` | `/api/endpoints` | List endpoints with status |
| `POST` | `/api/endpoints` | Register a new endpoint |
| `DELETE` | `/api/endpoints/{endpoint_id}` | Unregister an endpoint |
| `GET` | `/api/users` | List all known users |
| `POST` | `/api/users/{user_id}/bind` | Bind user to an endpoint |
| `POST` | `/api/users/{user_id}/unbind` | Unbind user from an endpoint |
| `GET` | `/api/invites` | List active invite codes |
| `POST` | `/api/invites` | Create a new invite code |

### `gateway.cli` — CLI (`clawbot-gateway`)

```bash
clawbot-gateway init                    # Scaffold gateway.yaml
clawbot-gateway start [--config PATH]   # Start the gateway
clawbot-gateway stop                    # Stop via PID file
clawbot-gateway status                  # Local or remote status

clawbot-gateway account add             # QR login to add a Bot account
clawbot-gateway account list            # List configured accounts
clawbot-gateway account remove <id>     # Remove an account
clawbot-gateway account status [<id>]   # Show account status

clawbot-gateway user list               # List all users
clawbot-gateway user info <user_id>     # Show user info
clawbot-gateway user allow <user_id>    # Allow a user
clawbot-gateway user block <user_id>    # Block a user
clawbot-gateway user bind <user_id> <endpoint_id>    # Bind user to endpoint
clawbot-gateway user unbind <user_id> <endpoint_id>  # Unbind user

clawbot-gateway endpoint list           # List endpoints
clawbot-gateway endpoint add <id> [--name NAME] [--type TYPE] [--url URL]
clawbot-gateway endpoint remove <id>

clawbot-gateway invite list             # List active invite codes
clawbot-gateway invite create <endpoint_id> [--max-uses N] [--ttl HOURS]

clawbot-gateway logs [-n LINES] [--endpoint ID] [--user ID]
```

Global flags: `--config PATH`, `--json`, `--yes`, `--gateway URL`, `--admin-token TOKEN`.

Remote management: when `--gateway URL` is provided (or `CLAWBOT_GATEWAY_URL` env), most subcommands talk to the running gateway's Admin API instead of reading local config.

---

## `wechat_clawbot.sdk.client` — SDK Client *(v0.4.0+)*

Connects to the gateway via WebSocket for custom bot development. Requires the `sdk` extra: `pip install wechat-clawbot[sdk]`.

```python
@dataclass
class Message:
    sender_id: str
    text: str
    context_token: str | None = None

class ClawBotClient:
    def __init__(
        self,
        gateway_url: str,
        endpoint_id: str,
        token: str = "",
        reconnect: bool = True,
        reconnect_delay: float = 5.0,
    ) -> None: ...

    @property
    def ws_url(self) -> str                        # computed WebSocket URL

    async def __aenter__(self) -> ClawBotClient
    async def __aexit__(self, *args) -> None

    async def connect(self) -> None
    async def close(self) -> None
    async def messages(self) -> AsyncIterator[Message]   # iterate incoming messages
    async def reply(self, sender_id: str, text: str) -> None
    async def ping(self) -> None
```

Usage example:

```python
async with ClawBotClient("http://localhost:8765", "my-endpoint") as client:
    async for msg in client.messages():
        await client.reply(msg.sender_id, f"Echo: {msg.text}")
```
