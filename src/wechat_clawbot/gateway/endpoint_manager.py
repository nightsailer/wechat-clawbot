"""Endpoint manager — registry of configured endpoints with runtime status.

Tracks all configured endpoints, their online/offline state, and provides
filtering helpers used by routing and command handlers.
"""

from __future__ import annotations

import logging
import time

from .types import EndpointConfig, EndpointInfo, EndpointStatus

logger = logging.getLogger(__name__)


class EndpointManager:
    """Registry of all configured endpoints with their runtime status.

    Endpoints are registered at startup from the gateway configuration.
    Sub-channels call :meth:`set_connected` when an upstream MCP/SDK/HTTP
    client connects or disconnects so the manager can track live status.
    """

    def __init__(self) -> None:
        self._endpoints: dict[str, EndpointInfo] = {}

    # ---- registration --------------------------------------------------------

    def register(self, config: EndpointConfig) -> None:
        """Register an endpoint from configuration.

        If the endpoint is already registered, its config is updated
        while preserving runtime status.
        """
        existing = self._endpoints.get(config.id)
        if existing:
            existing.config = config
            logger.debug("Updated endpoint config: %s", config.id)
        else:
            self._endpoints[config.id] = EndpointInfo(config=config)
            logger.info("Registered endpoint: %s (%s)", config.id, config.name)

    def unregister(self, endpoint_id: str) -> None:
        """Remove an endpoint from the registry."""
        removed = self._endpoints.pop(endpoint_id, None)
        if removed:
            logger.info("Unregistered endpoint: %s", endpoint_id)

    # ---- queries -------------------------------------------------------------

    def get_endpoint(self, endpoint_id: str) -> EndpointInfo | None:
        """Get endpoint info by ID, or ``None`` if not found."""
        return self._endpoints.get(endpoint_id)

    def get_endpoint_by_name(self, name: str) -> EndpointInfo | None:
        """Look up an endpoint by its display name (case-insensitive).

        Returns the first match, or ``None``.
        """
        name_lower = name.lower()
        for info in self._endpoints.values():
            if info.config.name.lower() == name_lower:
                return info
        # Also try matching by ID
        for info in self._endpoints.values():
            if info.config.id.lower() == name_lower:
                return info
        return None

    def list_endpoints(self) -> list[EndpointInfo]:
        """Return all registered endpoints."""
        return list(self._endpoints.values())

    def list_endpoint_ids(self) -> list[str]:
        """Return all registered endpoint IDs."""
        return list(self._endpoints.keys())

    def is_online(self, endpoint_id: str) -> bool:
        """Check if an endpoint is currently online."""
        info = self._endpoints.get(endpoint_id)
        return info is not None and info.status == EndpointStatus.ONLINE

    # ---- status updates ------------------------------------------------------

    def set_connected(self, endpoint_id: str, connected: bool) -> None:
        """Update endpoint connection status.

        Called by sub-channels when an upstream client connects or disconnects.
        """
        info = self._endpoints.get(endpoint_id)
        if info is None:
            logger.warning(
                "set_connected called for unknown endpoint: %s (connected=%s)",
                endpoint_id,
                connected,
            )
            return

        if connected:
            info.status = EndpointStatus.ONLINE
            info.connected_at = time.time()
            info.error_message = ""
            logger.info("Endpoint %s is now ONLINE", endpoint_id)
        else:
            info.status = EndpointStatus.OFFLINE
            logger.info("Endpoint %s is now OFFLINE", endpoint_id)

    def set_error(self, endpoint_id: str, message: str) -> None:
        """Mark an endpoint as having an error."""
        info = self._endpoints.get(endpoint_id)
        if info is None:
            return
        info.status = EndpointStatus.ERROR
        info.error_message = message
        logger.warning("Endpoint %s error: %s", endpoint_id, message)

    # ---- filtering -----------------------------------------------------------

    def get_endpoints_for_user(self, user_bindings: list[str]) -> list[EndpointInfo]:
        """Return endpoints that match the user's binding list.

        Only returns endpoints that are both registered and bound by the user.
        """
        result = []
        for eid in user_bindings:
            info = self._endpoints.get(eid)
            if info is not None:
                result.append(info)
        return result

    def get_online_count(self) -> int:
        """Return the number of currently online endpoints."""
        return sum(1 for info in self._endpoints.values() if info.status == EndpointStatus.ONLINE)
