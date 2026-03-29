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

from .channels.mcp_channel import MCPChannel
from .config import GatewayConfig, resolve_gateway_state_dir
from .delivery import DeliveryQueue
from .poller import Poller
from .types import DeliveryRecord, DeliveryStatus, InboundMessage

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

    async def start(self) -> None:
        """Start the gateway."""
        logger.info("Starting gateway...")

        # Init delivery queue
        db_path = self._state_dir / "gateway.db"
        self._delivery = DeliveryQueue(db_path)
        await self._delivery.open()

        # Init MCP channel
        self._mcp_channel = MCPChannel(
            on_reply=self._handle_reply,
            on_send_file=self._handle_send_file,
            on_typing=self._handle_typing,
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

    async def _on_inbound_message(self, msg: InboundMessage) -> None:
        """Handle an inbound WeChat message."""
        # Get first endpoint (Phase 1: single endpoint)
        endpoint_id = next(iter(self._config.endpoints))

        # Enqueue for delivery guarantee
        record = DeliveryRecord(
            message_id=msg.message_id or str(uuid.uuid4()),
            account_id=msg.account_id,
            sender_id=msg.sender_id,
            endpoint_id=endpoint_id,
            content=msg.text,
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
                sender_id=msg.sender_id,
                text=msg.text,
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

        # Retrieve cached context token for this account+user pair
        ctx_token = get_context_token(account_id, sender_id)

        return WeixinApiOptions(
            base_url=base_url,
            token=token,
            context_token=ctx_token,
        )

    async def _handle_reply(self, endpoint_id: str, sender_id: str, text: str) -> None:
        """Handle wechat_reply from an MCP endpoint."""
        account_id = next(iter(self._config.accounts))
        opts = self._resolve_account_api_options(account_id, sender_id)

        await send_message_weixin(sender_id, text, opts)
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
