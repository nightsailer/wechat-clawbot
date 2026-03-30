"""Gateway application — main orchestrator."""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path

import anyio

from wechat_clawbot.api.client import WeixinApiOptions
from wechat_clawbot.messaging.inbound import get_context_token
from wechat_clawbot.messaging.send import send_message_weixin

from .auth import AuthZModule
from .channels.mcp_channel import MCPChannel
from .commands import GatewayCommandContext, handle_command
from .config import GatewayConfig, resolve_gateway_state_dir
from .delivery import DeliveryQueue
from .endpoint_manager import EndpointManager
from .poller import Poller
from .router import Router
from .session import SessionStore
from .types import (
    DeliveryRecord,
    DeliveryStatus,
    EndpointConfig,
    InboundMessage,
    RouteType,
)

logger = logging.getLogger(__name__)


class GatewayApp:
    """Main gateway application."""

    def __init__(self, config: GatewayConfig) -> None:
        self._config = config
        self._state_dir = resolve_gateway_state_dir()
        self._delivery: DeliveryQueue | None = None
        self._mcp_channel: MCPChannel | None = None
        self._poller: Poller | None = None
        self._stop_event: anyio.Event | None = None
        self._session_store: SessionStore | None = None
        self._authz: AuthZModule | None = None
        self._endpoint_manager: EndpointManager | None = None
        self._router: Router | None = None

    async def start(self) -> None:
        """Start the gateway."""
        logger.info("Starting gateway...")

        # Init session store and authorization
        users_dir = self._state_dir / "users"
        self._session_store = SessionStore(users_dir)
        self._authz = AuthZModule(self._config.authorization)

        # Init endpoint manager from config
        self._endpoint_manager = EndpointManager()
        for ep_id, ep_cfg in self._config.endpoints.items():
            self._endpoint_manager.register(
                EndpointConfig(
                    id=ep_id,
                    name=ep_cfg.name or ep_id,
                    type=ep_cfg.type,
                    url=ep_cfg.url,
                    tags=ep_cfg.tags,
                    api_key=ep_cfg.api_key,
                    description=ep_cfg.description,
                )
            )

        # Init router
        self._router = Router(
            config=self._config.routing,
            session_store=self._session_store,
            endpoint_manager=self._endpoint_manager,
        )

        # Init delivery queue
        db_path = self._state_dir / "gateway.db"
        self._delivery = DeliveryQueue(db_path)
        await self._delivery.open()

        # Init MCP channel with connect/disconnect callbacks
        self._mcp_channel = MCPChannel(
            on_reply=self._handle_reply,
            on_send_file=self._handle_send_file,
            on_typing=self._handle_typing,
            on_connect=self._on_endpoint_connected,
            on_disconnect=self._on_endpoint_disconnected,
        )

        # Get first account config
        account_id = next(iter(self._config.accounts))
        account_cfg = self._config.accounts[account_id]

        # Load account credentials (read from credentials file or use inline)
        token = account_cfg.token
        base_url = account_cfg.base_url

        if account_cfg.credentials and not token:
            # Load from credentials file
            cred_path = Path(account_cfg.credentials).expanduser()
            if cred_path.exists():
                cred_data = json.loads(cred_path.read_text())
                token = cred_data.get("token", "")
                base_url = cred_data.get("baseUrl", base_url)

        # Init poller
        self._poller = Poller(
            account_id=account_id,
            base_url=base_url,
            token=token,
            on_message=self._on_inbound_message,
            state_dir=self._state_dir,
        )

        # Run poller + HTTP server concurrently
        self._stop_event = anyio.Event()

        assert self._poller is not None
        assert self._stop_event is not None
        async with anyio.create_task_group() as tg:
            tg.start_soon(self._poller.run, self._stop_event)
            tg.start_soon(self._run_http_server)
            logger.info("Gateway started successfully")
            # Wait for stop signal
            await self._stop_event.wait()
            tg.cancel_scope.cancel()

    async def stop(self) -> None:
        """Stop the gateway gracefully."""
        logger.info("Stopping gateway...")
        if self._stop_event:
            self._stop_event.set()
        if self._mcp_channel:
            await self._mcp_channel.stop()
        if self._delivery:
            await self._delivery.close()
        logger.info("Gateway stopped")

    async def _run_http_server(self) -> None:
        """Run the HTTP server for MCP SSE endpoints."""
        import uvicorn

        assert self._mcp_channel is not None
        app = self._mcp_channel.get_asgi_app()
        config = uvicorn.Config(
            app,
            host=self._config.gateway.host,
            port=self._config.gateway.port,
            log_level=self._config.gateway.log_level,
        )
        server = uvicorn.Server(config)
        await server.serve()

    # ---- endpoint connect/disconnect callbacks --------------------------------

    def _on_endpoint_connected(self, endpoint_id: str) -> None:
        """Called by MCP channel when an endpoint connects."""
        if self._endpoint_manager:
            self._endpoint_manager.set_connected(endpoint_id, connected=True)

    def _on_endpoint_disconnected(self, endpoint_id: str) -> None:
        """Called by MCP channel when an endpoint disconnects."""
        if self._endpoint_manager:
            self._endpoint_manager.set_connected(endpoint_id, connected=False)

    # ---- inbound message handling --------------------------------------------

    async def _on_inbound_message(self, msg: InboundMessage) -> None:
        """Handle an inbound WeChat message with multi-endpoint routing."""
        assert self._session_store is not None
        assert self._authz is not None
        assert self._router is not None
        assert self._endpoint_manager is not None

        sender_id = msg.sender_id
        account_id = msg.account_id

        # 1. Look up user by sender_id
        user = self._session_store.get_user(sender_id)

        if user is None:
            # 2. New user: check authorization
            if not self._authz.is_allowed(sender_id):
                logger.warning("Unauthorized user %s rejected", sender_id)
                await self._send_gateway_message(
                    account_id, sender_id, "You are not authorized to use this gateway."
                )
                return

            # Create user with default endpoints and appropriate role
            role = self._authz.get_role(sender_id)
            default_eps = self._authz.default_endpoints
            if not default_eps:
                # Fall back to all configured endpoints
                default_eps = list(self._config.endpoints.keys())

            user = self._session_store.create_user(
                user_id=sender_id,
                role=role,
                default_endpoints=default_eps,
            )
            logger.info("Created new user %s with role=%s", sender_id, role.value)
            await self._send_gateway_message(
                account_id,
                sender_id,
                f"Welcome! You are connected to endpoint: {user.active_endpoint}",
            )

        # Store context token if present
        if msg.context_token:
            self._session_store.set_context_token(account_id, sender_id, msg.context_token)

        # 3. Route the message
        route = self._router.resolve(sender_id, msg.text)

        # 4. Handle by route type
        if route.type == RouteType.GATEWAY_COMMAND:
            await self._handle_gateway_command(account_id, sender_id, route.command, route.command_args, route.error)
            return

        if route.type == RouteType.COMMAND_TO:
            if route.error:
                await self._send_gateway_message(account_id, sender_id, route.error)
                return
            await self._deliver_to_endpoint(
                account_id, sender_id, route.endpoint_id, route.cleaned_text, msg
            )
            return

        if route.type == RouteType.MENTION:
            if not route.endpoint_id:
                # Mention didn't resolve — shouldn't happen since router returns None
                await self._send_gateway_message(
                    account_id, sender_id, "Endpoint not found."
                )
                return
            await self._deliver_to_endpoint(
                account_id, sender_id, route.endpoint_id, route.cleaned_text, msg
            )
            return

        # ACTIVE_ENDPOINT (default)
        if route.error:
            await self._send_gateway_message(
                account_id, sender_id, "No active endpoint. Use /use <name> to select one."
            )
            return

        await self._deliver_to_endpoint(
            account_id, sender_id, route.endpoint_id, route.cleaned_text, msg
        )

    async def _handle_gateway_command(
        self,
        account_id: str,
        sender_id: str,
        command: str,
        args: str,
        error: str,
    ) -> None:
        """Process a gateway command and send the response."""
        assert self._session_store is not None
        assert self._endpoint_manager is not None
        assert self._authz is not None

        if error:
            await self._send_gateway_message(account_id, sender_id, error)
            return

        ctx = GatewayCommandContext(
            sender_id=sender_id,
            account_id=account_id,
            command=command,
            args=args,
            session_store=self._session_store,
            endpoint_manager=self._endpoint_manager,
            authz=self._authz,
        )
        response = await handle_command(ctx)
        await self._send_gateway_message(account_id, sender_id, response)

    async def _deliver_to_endpoint(
        self,
        account_id: str,
        sender_id: str,
        endpoint_id: str,
        text: str,
        msg: InboundMessage,
    ) -> None:
        """Deliver a message to a specific endpoint."""
        # Enqueue for delivery guarantee
        record = DeliveryRecord(
            message_id=msg.message_id or str(uuid.uuid4()),
            account_id=account_id,
            sender_id=sender_id,
            endpoint_id=endpoint_id,
            content=text,
            context_token=msg.context_token,
            status=DeliveryStatus.PENDING,
            created_at=msg.timestamp or time.time(),
        )
        assert self._delivery is not None
        await self._delivery.enqueue(record)

        # Try to deliver
        if self._mcp_channel and self._mcp_channel.is_endpoint_connected(endpoint_id):
            success = await self._mcp_channel.deliver_message(
                endpoint_id=endpoint_id,
                sender_id=sender_id,
                text=text,
                context_token=msg.context_token,
            )
            if success:
                assert self._delivery is not None
                await self._delivery.mark_delivered(record.message_id)
            else:
                logger.warning("Failed to deliver to %s, will retry", endpoint_id)
        else:
            logger.warning("Endpoint %s not connected, message queued", endpoint_id)

    def _resolve_account_api_options(self, account_id: str, sender_id: str) -> WeixinApiOptions:
        """Build WeixinApiOptions for the given account and sender."""
        account_cfg = self._config.accounts[account_id]
        token = account_cfg.token
        base_url = account_cfg.base_url

        # Load token from credentials if needed
        if account_cfg.credentials and not token:
            cred_path = Path(account_cfg.credentials).expanduser()
            if cred_path.exists():
                cred_data = json.loads(cred_path.read_text())
                token = cred_data.get("token", "")
                base_url = cred_data.get("baseUrl", base_url)

        # Retrieve cached context token via session store or fallback
        ctx_token: str | None = None
        if self._session_store:
            ctx_token = self._session_store.get_context_token(account_id, sender_id)
        else:
            ctx_token = get_context_token(account_id, sender_id)

        return WeixinApiOptions(
            base_url=base_url,
            token=token,
            context_token=ctx_token,
        )

    async def _handle_reply(self, endpoint_id: str, sender_id: str, text: str) -> None:
        """Handle wechat_reply from an MCP endpoint.

        If the reply comes from a non-active endpoint, prefix it with the
        endpoint name so the user knows which endpoint is responding.
        """
        account_id = next(iter(self._config.accounts))
        opts = self._resolve_account_api_options(account_id, sender_id)

        # Add endpoint name prefix if reply is from non-active endpoint
        reply_text = text
        if self._session_store and self._endpoint_manager:
            active = self._session_store.get_active_endpoint(sender_id)
            if active and endpoint_id != active:
                info = self._endpoint_manager.get_endpoint(endpoint_id)
                name = info.config.name if info else endpoint_id
                reply_text = f"[{name}] {text}"

        await send_message_weixin(sender_id, reply_text, opts)
        logger.info("Reply sent to %s via account %s", sender_id, account_id)

    async def _handle_send_file(
        self, endpoint_id: str, sender_id: str, file_path: str, text: str
    ) -> None:
        """Handle wechat_send_file from an MCP endpoint."""
        # TODO: implement in Phase 1 enhancement
        logger.warning("send_file not yet implemented in gateway mode")

    async def _handle_typing(self, endpoint_id: str, sender_id: str) -> None:
        """Handle wechat_typing from an MCP endpoint."""
        # TODO: implement typing indicator
        logger.warning("typing not yet implemented in gateway mode")

    async def _send_gateway_message(
        self, account_id: str, sender_id: str, text: str
    ) -> None:
        """Send a gateway-originated message directly to a user."""
        try:
            opts = self._resolve_account_api_options(account_id, sender_id)
            await send_message_weixin(sender_id, text, opts)
            logger.info("Gateway message sent to %s: %s", sender_id, text[:50])
        except Exception:
            logger.exception("Failed to send gateway message to %s", sender_id)
