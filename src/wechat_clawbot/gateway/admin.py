"""Admin HTTP API for gateway management.

Provides a separate HTTP server (on ``admin_port``) that exposes JSON
endpoints for managing accounts, endpoints, users, and invite codes.
Protected by Bearer-token authentication when ``admin_token`` is set.
"""

from __future__ import annotations

import hmac
import logging
import time
from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request  # noqa: TCH002 — needed at runtime
from starlette.responses import JSONResponse
from starlette.routing import Route

if TYPE_CHECKING:
    from .config import GatewayConfig
    from .endpoint_manager import EndpointManager
    from .invite import InviteManager
    from .poller import PollerManager
    from .session import SessionStore

logger = logging.getLogger(__name__)


class _BearerAuthMiddleware(BaseHTTPMiddleware):
    """Reject requests without a valid Bearer token."""

    def __init__(self, app: Starlette, token: str) -> None:  # type: ignore[override]
        super().__init__(app)
        self._token = token

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:], self._token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


class AdminAPI:
    """Admin HTTP API for gateway management."""

    def __init__(
        self,
        config: GatewayConfig,
        session_store: SessionStore,
        endpoint_manager: EndpointManager,
        invite_manager: InviteManager,
        poller_manager: PollerManager | None = None,
    ) -> None:
        self._config = config
        self._session_store = session_store
        self._endpoint_manager = endpoint_manager
        self._invite_manager = invite_manager
        self._poller_manager = poller_manager

    def get_asgi_app(self) -> Starlette:
        """Build and return the Starlette ASGI application."""
        routes = [
            Route("/api/status", self._get_status, methods=["GET"]),
            Route("/api/accounts", self._list_accounts, methods=["GET"]),
            Route("/api/endpoints", self._list_endpoints, methods=["GET"]),
            Route("/api/endpoints", self._add_endpoint, methods=["POST"]),
            Route("/api/endpoints/{endpoint_id}", self._remove_endpoint, methods=["DELETE"]),
            Route("/api/users", self._list_users, methods=["GET"]),
            Route("/api/users/{user_id}/bind", self._bind_user, methods=["POST"]),
            Route("/api/users/{user_id}/unbind", self._unbind_user, methods=["POST"]),
            Route("/api/invites", self._list_invites, methods=["GET"]),
            Route("/api/invites", self._create_invite, methods=["POST"]),
        ]

        middleware: list[Middleware] = []
        token = self._config.gateway.admin_token
        if token:
            middleware.append(Middleware(_BearerAuthMiddleware, token=token))

        return Starlette(routes=routes, middleware=middleware)

    # ---- handlers ---------------------------------------------------------------

    async def _get_status(self, request: Request) -> JSONResponse:
        """GET /api/status — overall gateway status."""
        endpoints = self._endpoint_manager.list_endpoints()
        online = self._endpoint_manager.get_online_count()
        users = self._session_store.list_users()
        accounts = self._poller_manager.account_ids if self._poller_manager else []

        return JSONResponse(
            {
                "status": "running",
                "time": time.time(),
                "accounts": len(accounts),
                "endpoints": {
                    "total": len(endpoints),
                    "online": online,
                },
                "users": len(users),
            }
        )

    async def _list_accounts(self, request: Request) -> JSONResponse:
        """GET /api/accounts — list configured Bot accounts."""
        accounts = []
        for aid, acfg in self._config.accounts.items():
            accounts.append(
                {
                    "id": aid,
                    "base_url": acfg.base_url,
                    "has_token": bool(acfg.token),
                    "has_credentials": bool(acfg.credentials),
                }
            )
        return JSONResponse({"accounts": accounts})

    async def _list_endpoints(self, request: Request) -> JSONResponse:
        """GET /api/endpoints — list all endpoints with status."""
        endpoints = []
        for info in self._endpoint_manager.list_endpoints():
            endpoints.append(
                {
                    "id": info.config.id,
                    "name": info.config.name,
                    "type": info.config.type.value,
                    "status": info.status.value,
                    "tags": info.config.tags,
                    "description": info.config.description,
                }
            )
        return JSONResponse({"endpoints": endpoints})

    async def _add_endpoint(self, request: Request) -> JSONResponse:
        """POST /api/endpoints — register a new endpoint at runtime."""
        from .types import ChannelType, EndpointConfig

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON body"}, status_code=400)

        ep_id = body.get("id", "")
        if not ep_id:
            return JSONResponse({"error": "id is required"}, status_code=400)

        existing = self._endpoint_manager.get_endpoint(ep_id)
        if existing:
            return JSONResponse({"error": f"endpoint {ep_id} already exists"}, status_code=409)

        ep_type_str = body.get("type", "mcp")
        try:
            ep_type = ChannelType(ep_type_str)
        except ValueError:
            return JSONResponse({"error": f"invalid type: {ep_type_str}"}, status_code=400)

        config = EndpointConfig(
            id=ep_id,
            name=body.get("name", ep_id),
            type=ep_type,
            url=body.get("url", ""),
            tags=body.get("tags", []),
            api_key=body.get("api_key", ""),
            description=body.get("description", ""),
        )
        self._endpoint_manager.register(config)
        return JSONResponse({"status": "created", "id": ep_id}, status_code=201)

    async def _remove_endpoint(self, request: Request) -> JSONResponse:
        """DELETE /api/endpoints/{endpoint_id} — unregister an endpoint."""
        endpoint_id = request.path_params["endpoint_id"]
        info = self._endpoint_manager.get_endpoint(endpoint_id)
        if not info:
            return JSONResponse({"error": "endpoint not found"}, status_code=404)
        self._endpoint_manager.unregister(endpoint_id)
        return JSONResponse({"status": "removed", "id": endpoint_id})

    async def _list_users(self, request: Request) -> JSONResponse:
        """GET /api/users — list all known users."""
        users = []
        for u in self._session_store.list_users():
            users.append(
                {
                    "user_id": u.user_id,
                    "display_name": u.display_name,
                    "role": u.role.value,
                    "active_endpoint": u.active_endpoint,
                    "account_id": u.account_id,
                    "bindings": [b.endpoint_id for b in u.bindings],
                    "last_active_at": u.last_active_at,
                }
            )
        return JSONResponse({"users": users})

    async def _bind_user(self, request: Request) -> JSONResponse:
        """POST /api/users/{user_id}/bind — bind user to an endpoint."""
        user_id = request.path_params["user_id"]
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON body"}, status_code=400)

        endpoint_id = body.get("endpoint_id", "")
        if not endpoint_id:
            return JSONResponse({"error": "endpoint_id is required"}, status_code=400)

        user = self._session_store.get_user(user_id)
        if not user:
            return JSONResponse({"error": "user not found"}, status_code=404)

        ep = self._endpoint_manager.get_endpoint(endpoint_id)
        if not ep:
            return JSONResponse({"error": "endpoint not found"}, status_code=404)

        ok = self._session_store.bind_endpoint(user_id, endpoint_id)
        if not ok:
            return JSONResponse({"error": "bind failed"}, status_code=500)
        return JSONResponse({"status": "bound", "user_id": user_id, "endpoint_id": endpoint_id})

    async def _unbind_user(self, request: Request) -> JSONResponse:
        """POST /api/users/{user_id}/unbind — unbind user from an endpoint."""
        user_id = request.path_params["user_id"]
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON body"}, status_code=400)

        endpoint_id = body.get("endpoint_id", "")
        if not endpoint_id:
            return JSONResponse({"error": "endpoint_id is required"}, status_code=400)

        user = self._session_store.get_user(user_id)
        if not user:
            return JSONResponse({"error": "user not found"}, status_code=404)

        ok = self._session_store.unbind_endpoint(user_id, endpoint_id)
        if not ok:
            return JSONResponse({"error": "unbind failed"}, status_code=500)
        return JSONResponse(
            {
                "status": "unbound",
                "user_id": user_id,
                "endpoint_id": endpoint_id,
            }
        )

    async def _list_invites(self, request: Request) -> JSONResponse:
        """GET /api/invites — list active invite codes."""
        invites = []
        for inv in self._invite_manager.list_active():
            invites.append(
                {
                    "code": inv.code,
                    "endpoint_id": inv.endpoint_id,
                    "max_uses": inv.max_uses,
                    "used_count": inv.used_count,
                    "expires_at": inv.expires_at,
                    "created_at": inv.created_at,
                }
            )
        return JSONResponse({"invites": invites})

    async def _create_invite(self, request: Request) -> JSONResponse:
        """POST /api/invites — create a new invite code."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON body"}, status_code=400)

        endpoint_id = body.get("endpoint_id", "")
        if not endpoint_id:
            return JSONResponse({"error": "endpoint_id is required"}, status_code=400)

        ep = self._endpoint_manager.get_endpoint(endpoint_id)
        if not ep:
            return JSONResponse({"error": "endpoint not found"}, status_code=404)

        max_uses = body.get("max_uses", 1)
        ttl_hours = body.get("ttl_hours", 0)

        code = self._invite_manager.create(
            endpoint_id=endpoint_id,
            max_uses=max_uses,
            ttl_hours=ttl_hours,
        )
        return JSONResponse({"code": code, "endpoint_id": endpoint_id}, status_code=201)
