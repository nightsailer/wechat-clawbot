"""Shared MCP tool definitions and instructions for WeChat channels.

Both the gateway MCP channel and the standalone claude_channel server
import from here to avoid duplicating tool schemas and instructions.
"""

from __future__ import annotations

from mcp.types import JSONRPCNotification
from mcp.types import Tool as MCPTool

INSTRUCTIONS = "\n".join(
    [
        'Messages from WeChat users arrive as <channel source="wechat" sender="..." sender_id="...">',
        "Reply using the wechat_reply tool. You MUST pass the sender_id from the inbound tag.",
        "To send a file (image, video, or document), use the wechat_send_file tool.",
        "IMPORTANT: When you start processing a WeChat message, call wechat_typing FIRST "
        "so the user sees a typing indicator. It auto-cancels when you send a reply.",
        "Messages are from real WeChat users via the WeChat ClawBot interface.",
        "Respond naturally in Chinese unless the user writes in another language.",
        "Keep replies concise — WeChat is a chat app, not an essay platform.",
        "WeChat supports basic Markdown: **bold**, *italic*, `code`, ```code blocks```, "
        "[links](url), ordered/unordered lists, and > blockquotes. "
        "Do NOT use # headings (rendered poorly) or ~~strikethrough~~ (not supported). "
        "Do NOT use # as a hashtag prefix — WeChat interprets #text as a tag link.",
    ]
)

TOOLS: list[MCPTool] = [
    MCPTool(
        name="wechat_reply",
        description="Send a text reply back to the WeChat user",
        inputSchema={
            "type": "object",
            "properties": {
                "sender_id": {
                    "type": "string",
                    "description": (
                        "The sender_id from the inbound <channel> tag (xxx@im.wechat format)"
                    ),
                },
                "text": {
                    "type": "string",
                    "description": "The plain-text message to send (no markdown)",
                },
            },
            "required": ["sender_id", "text"],
        },
    ),
    MCPTool(
        name="wechat_send_file",
        description=(
            "Send a file (image, video, or document) to the WeChat user. "
            "The file type is auto-detected from the file extension."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "sender_id": {
                    "type": "string",
                    "description": (
                        "The sender_id from the inbound <channel> tag (xxx@im.wechat format)"
                    ),
                },
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the local file to send",
                },
                "text": {
                    "type": "string",
                    "description": "Optional caption text to accompany the file",
                    "default": "",
                },
            },
            "required": ["sender_id", "file_path"],
        },
    ),
    MCPTool(
        name="wechat_typing",
        description=(
            "Show a typing indicator to the WeChat user. "
            "Call this when you START processing a WeChat message. "
            "Automatically cancelled when you call wechat_reply or wechat_send_file."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "sender_id": {
                    "type": "string",
                    "description": (
                        "The sender_id from the inbound <channel> tag (xxx@im.wechat format)"
                    ),
                },
            },
            "required": ["sender_id"],
        },
    ),
]


def build_channel_notification(sender_id: str, text: str) -> JSONRPCNotification:
    """Create a ``notifications/claude/channel`` JSON-RPC notification."""
    return JSONRPCNotification(
        jsonrpc="2.0",
        method="notifications/claude/channel",
        params={
            "content": text,
            "meta": {
                "sender": sender_id.split("@")[0] if "@" in sender_id else sender_id,
                "sender_id": sender_id,
            },
        },
    )
