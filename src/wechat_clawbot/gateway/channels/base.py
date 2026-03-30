"""Base protocol and shared callback types for sub-channel implementations."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

# Shared callback type aliases used across all sub-channels.
ReplyCallback = Callable[[str, str, str], Awaitable[None]]
"""(endpoint_id, sender_id, text) -> None"""

SendFileCallback = Callable[[str, str, str, str], Awaitable[None]]
"""(endpoint_id, sender_id, file_path, text) -> None"""

TypingCallback = Callable[[str, str], Awaitable[None]]
"""(endpoint_id, sender_id) -> None"""

ConnectCallback = Callable[[str], Any]
"""(endpoint_id) -> None  -- sync-compatible so no async wrappers needed."""

DisconnectCallback = Callable[[str], Any]
"""(endpoint_id) -> None  -- sync-compatible so no async wrappers needed."""


@runtime_checkable
class SubChannel(Protocol):
    """Protocol that all sub-channel types must implement.

    A sub-channel handles the transport between the gateway and upstream endpoints.
    """

    async def start(self) -> None:
        """Start the sub-channel (e.g., start HTTP server for SSE)."""
        ...

    async def stop(self) -> None:
        """Stop the sub-channel and clean up resources."""
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
        """Deliver a message to an upstream endpoint.

        Returns True if delivery was successful, False if endpoint is not connected.
        """
        ...

    async def send_reply(
        self,
        endpoint_id: str,
        sender_id: str,
        text: str,
        context_token: str | None = None,
    ) -> None:
        """Send a reply from the gateway back through this sub-channel.

        This is the reverse path — used when the gateway needs to push
        a message originated from another endpoint to the client connected
        via this sub-channel.
        """
        ...

    def is_endpoint_connected(self, endpoint_id: str) -> bool:
        """Check if a specific endpoint is currently connected."""
        ...

    def get_connected_endpoints(self) -> list[str]:
        """Return list of currently connected endpoint IDs."""
        ...
