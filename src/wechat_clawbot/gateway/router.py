"""Router engine — resolves inbound messages to endpoints.

Resolution order:
1. Gateway command (text starts with a configured command prefix like ``/``)
2. Mention (text starts with ``@endpoint_name``)
3. Default: active endpoint from user session
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .commands import GATEWAY_COMMANDS
from .types import RouteResult, RouteType

if TYPE_CHECKING:
    from .config import RoutingConfig
    from .endpoint_manager import EndpointManager
    from .session import SessionStore

logger = logging.getLogger(__name__)


class Router:
    """Route engine that resolves inbound messages to endpoints.

    Uses the routing configuration to determine whether a message is a
    gateway command, an ``@mention``, a ``/to`` one-shot, or should go
    to the user's active endpoint.
    """

    def __init__(
        self,
        config: RoutingConfig,
        session_store: SessionStore,
        endpoint_manager: EndpointManager,
    ) -> None:
        self._config = config
        self._session_store = session_store
        self._endpoint_manager = endpoint_manager

    def resolve(self, sender_id: str, text: str) -> RouteResult:
        """Resolve routing for an inbound message.

        Parameters
        ----------
        sender_id:
            The WeChat user ID of the message sender.
        text:
            The raw message text.

        Returns
        -------
        RouteResult
            Describes how the message should be handled.
        """
        stripped = text.strip()

        # 1. Check for gateway command prefix
        result = self._try_gateway_command(stripped)
        if result is not None:
            return result

        # 2. Check for @mention prefix
        result = self._try_mention(stripped)
        if result is not None:
            return result

        # 3. Default: route to active endpoint
        return self._route_active_endpoint(sender_id, stripped)

    def _try_gateway_command(self, text: str) -> RouteResult | None:
        """Check if text starts with a gateway command prefix followed by a known command."""
        for prefix in self._config.gateway_commands:
            if not text.startswith(prefix):
                continue

            # Extract the word after the prefix
            remainder = text[len(prefix) :]
            if not remainder:
                continue

            parts = remainder.split(None, 1)
            cmd = parts[0].lower()

            if cmd not in GATEWAY_COMMANDS:
                continue

            args = parts[1].strip() if len(parts) > 1 else ""

            # Special case: /to <name> <msg> is routed as COMMAND_TO
            if cmd == "to":
                return self._handle_command_to(args)

            return RouteResult(
                type=RouteType.GATEWAY_COMMAND,
                command=cmd,
                command_args=args,
                cleaned_text=text,
            )

        return None

    def _handle_command_to(self, args: str) -> RouteResult:
        """Parse ``/to <name> <message>`` and resolve the target endpoint."""
        if not args:
            return RouteResult(
                type=RouteType.GATEWAY_COMMAND,
                command="to",
                command_args="",
                error="Usage: /to <endpoint> <message>",
            )

        parts = args.split(None, 1)
        target_name = parts[0]
        message = parts[1].strip() if len(parts) > 1 else ""

        if not message:
            return RouteResult(
                type=RouteType.GATEWAY_COMMAND,
                command="to",
                command_args=args,
                error="Usage: /to <endpoint> <message>",
            )

        # Resolve endpoint by name or ID
        info = self._endpoint_manager.get_endpoint_by_name(target_name)
        if info is None:
            return RouteResult(
                type=RouteType.GATEWAY_COMMAND,
                command="to",
                command_args=args,
                error=f"Endpoint not found: {target_name}",
            )

        return RouteResult(
            type=RouteType.COMMAND_TO,
            endpoint_id=info.config.id,
            cleaned_text=message,
        )

    def _try_mention(self, text: str) -> RouteResult | None:
        """Check if text starts with ``@endpoint_name``."""
        mention_prefix = self._config.mention_prefix
        if not text.startswith(mention_prefix):
            return None

        # Extract the name after the prefix
        remainder = text[len(mention_prefix) :]
        if not remainder:
            return None

        parts = remainder.split(None, 1)
        target_name = parts[0]
        message = parts[1].strip() if len(parts) > 1 else ""

        # Resolve endpoint by name or ID
        info = self._endpoint_manager.get_endpoint_by_name(target_name)
        if info is None:
            # Not a valid mention — fall through to default routing
            return None

        return RouteResult(
            type=RouteType.MENTION,
            endpoint_id=info.config.id,
            cleaned_text=message,
        )

    def _route_active_endpoint(self, sender_id: str, text: str) -> RouteResult:
        """Route to the user's active endpoint."""
        active = self._session_store.get_active_endpoint(sender_id)
        if not active:
            return RouteResult(
                type=RouteType.ACTIVE_ENDPOINT,
                endpoint_id="",
                cleaned_text=text,
                error="No active endpoint",
            )

        return RouteResult(
            type=RouteType.ACTIVE_ENDPOINT,
            endpoint_id=active,
            cleaned_text=text,
        )
