# Gateway Design v2

> **Implementation Status: ALL 6 PHASES COMPLETE (2026-03-30)**
> Branch: `phase-6/http-channel-ops`
> Tests: 410 passed
> See CHANGELOG.md for feature summary

## Overview

The Gateway v2 design introduces M:N multi-user, multi-endpoint message routing for WeChat ClawBot. Multiple WeChat Bot accounts (downstream) route messages to multiple upstream AI endpoints via configurable sub-channels (MCP SSE, SDK WebSocket, HTTP Webhook).

## Core Components

### Router Engine
Resolves inbound messages to endpoints using three strategies:
1. Gateway commands (`/list`, `/use`, `/status`, etc.)
2. `@mention` prefix routing (`@endpoint-name message`)
3. Active endpoint (default — uses user's currently selected endpoint)

### Session Store
Per-user persistent state including:
- Active endpoint selection
- Endpoint bindings (which endpoints a user can access)
- Per-endpoint session context (context tokens, last message time)

### Delivery Queue
SQLite-backed (WAL mode) durable message queue with:
- Retry logic with exponential backoff
- Message expiry
- Survives process restarts

### Sub-Channels
Three transport types for connecting upstream endpoints:
- **MCP SSE** — SSE stream + JSON-RPC POST for MCP-compatible clients (Claude Code)
- **SDK WebSocket** — bidirectional WebSocket for custom bots using `ClawBotClient`
- **HTTP Webhook** — outbound POST to third-party services

### Authorization
Three modes:
- `allowlist` — only admin users can interact
- `open` — all users allowed
- `invite-code` — users must redeem a code to gain access

### Admin API
Separate Starlette HTTP server with Bearer token authentication for:
- Status monitoring
- Account, endpoint, user, and invite management

## Configuration

All settings defined in `~/.clawbot-gateway/gateway.yaml` using a Pydantic-validated schema (`GatewayConfig`).
