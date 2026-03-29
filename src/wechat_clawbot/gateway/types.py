"""Gateway core data types."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ChannelType(str, Enum):
    """Sub-channel transport type."""

    MCP = "mcp"
    SDK = "sdk"
    HTTP = "http"


class EndpointStatus(str, Enum):
    """Endpoint connection status."""

    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"


class DeliveryStatus(str, Enum):
    """Message delivery queue status."""

    PENDING = "pending"
    DELIVERED = "delivered"
    EXPIRED = "expired"


class UserRole(str, Enum):
    """User authorization role."""

    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"


class RouteType(str, Enum):
    """How a message was routed."""

    ACTIVE_ENDPOINT = "active-endpoint"
    MENTION = "mention"
    COMMAND_TO = "command-to"
    GATEWAY_COMMAND = "gateway-command"


@dataclass
class EndpointConfig:
    """Configuration for an upstream endpoint."""

    id: str
    name: str
    type: ChannelType
    url: str = ""
    tags: list[str] = field(default_factory=list)
    api_key: str = ""
    description: str = ""


@dataclass
class AccountConfig:
    """Configuration for a WeChat Bot account (downstream)."""

    id: str
    credentials_path: str = ""
    token: str = ""
    base_url: str = "https://ilinkai.weixin.qq.com"


@dataclass
class EndpointBinding:
    """A user's binding to an endpoint."""

    endpoint_id: str
    bound_at: float = field(default_factory=time.time)
    permissions: list[str] = field(default_factory=lambda: ["read", "write"])
    last_message_at: float = 0.0


@dataclass
class EndpointSession:
    """Per user-endpoint session state."""

    context_token: str | None = None
    last_message_at: float = 0.0
    state: dict[str, Any] = field(default_factory=dict)


@dataclass
class UserState:
    """Persistent state for a WeChat user."""

    user_id: str
    display_name: str = ""
    role: UserRole = UserRole.GUEST
    active_endpoint: str = ""
    bindings: list[EndpointBinding] = field(default_factory=list)
    endpoint_sessions: dict[str, EndpointSession] = field(default_factory=dict)
    account_id: str = ""
    created_at: float = field(default_factory=time.time)
    last_active_at: float = field(default_factory=time.time)

    def is_bound_to(self, endpoint_id: str) -> bool:
        """Check if user is bound to a specific endpoint."""
        return any(b.endpoint_id == endpoint_id for b in self.bindings)

    def get_binding(self, endpoint_id: str) -> EndpointBinding | None:
        """Get binding for a specific endpoint."""
        for b in self.bindings:
            if b.endpoint_id == endpoint_id:
                return b
        return None


@dataclass
class EndpointInfo:
    """Runtime endpoint info (config + status)."""

    config: EndpointConfig
    status: EndpointStatus = EndpointStatus.OFFLINE
    connected_at: float = 0.0
    last_active_at: float = 0.0
    error_message: str = ""


@dataclass
class RouteResult:
    """Result of routing a message."""

    type: RouteType
    endpoint_id: str = ""
    cleaned_text: str = ""
    command: str = ""
    command_args: str = ""
    error: str = ""


@dataclass
class DeliveryRecord:
    """A message in the delivery queue."""

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


@dataclass
class InboundMessage:
    """A processed inbound message from WeChat, ready for routing."""

    account_id: str
    sender_id: str
    text: str
    context_token: str | None = None
    message_id: str = ""
    timestamp: float = 0.0
    media_path: str = ""
    media_type: str = ""
