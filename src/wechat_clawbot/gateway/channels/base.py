"""Base protocol for sub-channel implementations."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


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
