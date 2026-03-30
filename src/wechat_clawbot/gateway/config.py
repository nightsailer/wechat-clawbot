"""Gateway configuration parser and gateway.yaml schema (Task 1.2).

Loads, validates, and scaffolds the ``~/.clawbot-gateway/gateway.yaml``
configuration file that drives the M:N gateway.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from wechat_clawbot.gateway.types import ChannelType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

DEFAULT_STATE_DIR = Path.home() / ".clawbot-gateway"
DEFAULT_CONFIG_NAME = "gateway.yaml"
ENV_CONFIG_PATH = "CLAWBOT_GATEWAY_CONFIG"


class GatewayServerConfig(BaseModel):
    """Core server settings (``gateway:`` section)."""

    host: str = "0.0.0.0"
    port: int = 8765
    admin_port: int = 8766
    admin_token: str = ""
    log_level: str = "info"


class AccountConfigModel(BaseModel):
    """A single WeChat Bot account (downstream).

    Supports either a path to a credentials JSON file **or** inline
    ``token`` / ``base_url`` values.
    """

    credentials: str | None = None
    token: str | None = None
    base_url: str = "https://ilinkai.weixin.qq.com"


class EndpointConfigModel(BaseModel):
    """An upstream endpoint definition."""

    name: str = ""
    type: ChannelType = ChannelType.MCP
    url: str = ""
    tags: list[str] = Field(default_factory=list)
    api_key: str = ""
    description: str = ""


class RoutingConfig(BaseModel):
    """Message routing strategy (``routing:`` section)."""

    strategy: Literal["active-endpoint", "prefix", "smart"] = "active-endpoint"
    mention_prefix: str = "@"
    gateway_commands: list[str] = Field(default_factory=lambda: ["/"])


class AuthorizationConfig(BaseModel):
    """User authorization (``authorization:`` section)."""

    mode: Literal["allowlist", "open", "invite-code"] = "allowlist"
    default_endpoints: list[str] = Field(default_factory=list)
    admins: list[str] = Field(default_factory=list)


class ArchiveConfig(BaseModel):
    """Message archive sidecar (``archive:`` section)."""

    enabled: bool = False
    storage: str = "sqlite"
    path: str = ""
    retention_days: int = 0


class GatewayConfig(BaseModel):
    """Root model for ``gateway.yaml``.

    Combines all sub-sections into a single validated configuration.
    """

    gateway: GatewayServerConfig = Field(default_factory=GatewayServerConfig)
    accounts: dict[str, AccountConfigModel] = Field(default_factory=dict)
    endpoints: dict[str, EndpointConfigModel] = Field(default_factory=dict)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    authorization: AuthorizationConfig = Field(default_factory=AuthorizationConfig)
    archive: ArchiveConfig = Field(default_factory=ArchiveConfig)

    @model_validator(mode="after")
    def _check_accounts_and_endpoints(self) -> GatewayConfig:
        """Ensure at least one account and one endpoint are defined."""
        if not self.accounts:
            raise ValueError("gateway.yaml must define at least one account under 'accounts:'")
        if not self.endpoints:
            raise ValueError("gateway.yaml must define at least one endpoint under 'endpoints:'")
        return self


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def resolve_gateway_state_dir() -> Path:
    """Return the gateway state directory (``~/.clawbot-gateway/``).

    Creates the directory if it does not already exist.
    """
    state_dir = DEFAULT_STATE_DIR
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def load_gateway_config(config_path: Path | None = None) -> GatewayConfig:
    """Load and validate ``gateway.yaml``.

    Resolution order for the config file path:
    1. Explicit *config_path* argument.
    2. ``CLAWBOT_GATEWAY_CONFIG`` environment variable.
    3. ``~/.clawbot-gateway/gateway.yaml`` (default).

    Raises
    ------
    FileNotFoundError
        If the resolved config file does not exist.
    ValueError
        If the YAML is invalid or fails validation.
    """
    if config_path is None:
        env_path = os.environ.get(ENV_CONFIG_PATH)
        config_path = Path(env_path) if env_path else DEFAULT_STATE_DIR / DEFAULT_CONFIG_NAME

    config_path = config_path.expanduser().resolve()
    if not config_path.exists():
        raise FileNotFoundError(
            f"Gateway config not found: {config_path}\n"
            f"Run 'clawbot-gateway init' or create the file manually."
        )

    try:
        import yaml  # noqa: PLC0415 — deferred import to tolerate missing pyyaml
    except ImportError as exc:
        raise ImportError(
            "pyyaml is required to parse gateway.yaml. Install it with:  pip install pyyaml"
        ) from exc

    raw_text = config_path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw_text)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping in {config_path}, got {type(data)}")

    return GatewayConfig.model_validate(data)


# ---------------------------------------------------------------------------
# Scaffold
# ---------------------------------------------------------------------------

_SCAFFOLD_TEMPLATE = """\
# ClawBot Gateway configuration
# Docs: https://github.com/nicedouble/wechat-clawbot

# -- Server -------------------------------------------------------------------
gateway:
  host: 0.0.0.0
  port: 8765
  admin_port: 8766
  admin_token: ""  # set a Bearer token to protect the admin API
  log_level: info

# -- WeChat Bot accounts (downstream) ----------------------------------------
accounts:
  main-bot:
    credentials: ~/.clawbot-gateway/accounts/main-bot.json

# -- Upstream endpoints -------------------------------------------------------
endpoints:
  my-endpoint:
    name: "My Endpoint"
    type: mcp
    url: "http://localhost:8080/sse"
    tags: [dev]

# -- Routing ------------------------------------------------------------------
routing:
  strategy: active-endpoint
  mention_prefix: "@"
  gateway_commands:
    - "/"

# -- Authorization ------------------------------------------------------------
authorization:
  mode: allowlist
  default_endpoints: []
  admins: []

# -- Archive (optional) -------------------------------------------------------
archive:
  enabled: false
  storage: sqlite
  path: ~/.clawbot-gateway/archive.db
  retention_days: 0
"""


def scaffold_gateway_config(state_dir: Path) -> Path:
    """Create a default ``gateway.yaml`` template under *state_dir*.

    Returns the path to the newly-created file.  If the file already exists
    it is **not** overwritten.
    """
    state_dir.mkdir(parents=True, exist_ok=True)
    config_path = state_dir / DEFAULT_CONFIG_NAME
    if config_path.exists():
        logger.info("gateway.yaml already exists at %s — skipping scaffold", config_path)
        return config_path

    config_path.write_text(_SCAFFOLD_TEMPLATE, encoding="utf-8")
    logger.info("Scaffolded gateway.yaml at %s", config_path)
    return config_path
