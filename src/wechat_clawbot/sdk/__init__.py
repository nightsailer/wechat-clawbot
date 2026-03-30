"""WeChat ClawBot SDK — client library for connecting custom bots to the gateway.

Provides :class:`ClawBotClient`, an async WebSocket client that connects to
the gateway's SDK sub-channel (``/sdk/{endpoint_id}/ws``).  Supports
auto-reconnect, an async message iterator, and a simple reply API.

Example::

    async with ClawBotClient(gateway_url="http://localhost:8765", endpoint_id="my-bot") as client:
        async for msg in client.messages():
            await client.reply(msg.sender_id, f"Echo: {msg.text}")
"""

from wechat_clawbot.sdk.client import ClawBotClient, Message

__all__ = ["ClawBotClient", "Message"]
