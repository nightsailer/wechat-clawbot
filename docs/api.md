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
    session_id: str | None
    message_type: int | None       # MessageType
    message_state: int | None      # MessageState
    item_list: list[MessageItem] | None
    context_token: str | None      # echo in replies to maintain session
```

#### `MessageItem`

```python
@dataclass
class MessageItem:
    type: int | None               # MessageItemType
    text_item: TextItem | None
    image_item: ImageItem | None
    voice_item: VoiceItem | None
    file_item: FileItem | None
    video_item: VideoItem | None
    ref_msg: RefMessage | None     # quoted message
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

## `wechat_clawbot.messaging.inbound` — Inbound Messages

```python
@dataclass
class WeixinMsgContext:
    body: str
    from_user: str
    to: str
    account_id: str
    originating_channel: str       # "openclaw-weixin"
    message_sid: str
    timestamp: int | None
    provider: str                  # "openclaw-weixin"
    chat_type: str                 # "direct"
    context_token: str | None
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
async def send_image_message_weixin(to, text, uploaded: UploadedFileInfo, opts) -> dict[str, str]
async def send_video_message_weixin(to, text, uploaded: UploadedFileInfo, opts) -> dict[str, str]
async def send_file_message_weixin(to, text, file_name, uploaded: UploadedFileInfo, opts) -> dict[str, str]
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

## `wechat_clawbot.claude_channel` — Claude Code Channel Bridge

### CLI (`wechat-clawbot-cc`)

```bash
wechat-clawbot-cc setup    # Interactive QR login
wechat-clawbot-cc serve    # Start MCP channel server
wechat-clawbot-cc help     # Show help
```

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

Starts the MCP server on stdio, registers the `wechat_reply` tool, and begins long-polling for WeChat messages.

#### MCP Tool: `wechat_reply`

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
