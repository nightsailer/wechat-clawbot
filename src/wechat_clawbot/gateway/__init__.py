"""WeChat ClawBot Gateway — M:N multi-user, multi-endpoint message routing gateway.

Routes messages from multiple WeChat Bot accounts (downstream) to multiple
upstream AI endpoints via configurable sub-channels (MCP SSE, SDK WebSocket,
HTTP Webhook).  Provides per-user session management, a durable SQLite-backed
delivery queue, authorization, invite codes, and an admin HTTP API.

Entry points:
    - CLI: ``clawbot-gateway`` (see :mod:`gateway.cli`)
    - Application: :class:`gateway.app.GatewayApp`
"""
