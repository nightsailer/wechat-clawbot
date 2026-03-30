"""WeChat ClawBot Gateway — multi-Bot, multi-endpoint message routing gateway.

Routes messages from multiple WeChat Bot accounts (downstream, each 1:1 bound
to its creator's WeChat account) to multiple upstream AI endpoints via
configurable sub-channels (MCP SSE, SDK WebSocket, HTTP Webhook).  Provides
per-Bot-owner session management, a durable SQLite-backed delivery queue,
authorization, invite codes, and an admin HTTP API.

Entry points:
    - CLI: ``clawbot-gateway`` (see :mod:`gateway.cli`)
    - Application: :class:`gateway.app.GatewayApp`
"""
