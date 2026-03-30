"""Sub-channel implementations for upstream endpoint connections.

Each sub-channel type provides a different transport mechanism for
connecting the gateway to upstream AI endpoints:

- :mod:`~.mcp_channel` — MCP SSE transport (``/mcp/{id}/sse``)
- :mod:`~.sdk_channel` — SDK WebSocket transport (``/sdk/{id}/ws``)
- :mod:`~.http_channel` — HTTP Webhook transport (``/http/{id}/webhook``)

All sub-channels implement the :class:`~.base.SubChannel` protocol.
"""
