"""ASGI authorization: cryptographically verify WebSockets and classify opaque mounts."""

from __future__ import annotations

from typing import Any

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.routing import Mount

from nabla.cloudflare_ops_access import (
    OwnerConfigError,
    OwnerKeysUnavailable,
    OwnerUnauthorized,
    assertion_from_headers,
    verify_owner_token,
)
from nabla.config_settings import get_settings
from nabla.homelab_trusted_ip import owner_source_permitted
from nabla.route_policy import Credential, route_policy_for, within


class OpsASGITransportGuard:
    """Fail closed on unknown mounted ASGI applications, independent of strict mode.

    HTTP RoutePolicy middleware still authorizes ordinary HTTP endpoints.
    Mounted sub-applications must have a classified owner path and a valid JWT,
    even before OPS_ROUTE_POLICY_STRICT is enabled.
    """

    def __init__(self, app: Any, root_app: Any | None = None) -> None:
        self.app = app
        self.root_app = root_app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        kind = scope.get("type")
        path = scope.get("path", "")
        if kind == "http" and self.root_app is not None:
            mounts = (route for route in self.root_app.router.routes if isinstance(route, Mount) and within(path, route.path))
            if any(mounts):
                policy = route_policy_for(path, kind="http")
                if policy.credential is not Credential.ACCESS_JWT:
                    response = JSONResponse(
                        {"detail": "Unapproved ASGI mount"},
                        status_code=403,
                        headers={"Cache-Control": "private, no-store"},
                    )
                    await response(scope, receive, send)
                    return
                try:
                    subject = await verify_owner_token(
                        assertion_from_headers(Headers(scope=scope)),
                    )
                except (OwnerConfigError, OwnerKeysUnavailable, OwnerUnauthorized):
                    response = JSONResponse(
                        {"detail": "Owner identity required"},
                        status_code=401,
                        headers={"Cache-Control": "private, no-store"},
                    )
                    await response(scope, receive, send)
                    return
                settings = get_settings()
                if not owner_source_permitted(scope, settings):
                    response = JSONResponse(
                        {"detail": "Owner network not authorized"},
                        status_code=403,
                        headers={"Cache-Control": "private, no-store"},
                    )
                    await response(scope, receive, send)
                    return
                scope.setdefault("state", {})["ops_owner_sub"] = subject
        elif kind == "websocket":
            policy = route_policy_for(path, kind="websocket")
            if policy.credential is not Credential.ACCESS_JWT:
                await send({"type": "websocket.close", "code": 4403})
                return
            try:
                subject = await verify_owner_token(
                    assertion_from_headers(Headers(scope=scope)),
                )
            except (OwnerConfigError, OwnerKeysUnavailable, OwnerUnauthorized):
                await send({"type": "websocket.close", "code": 4403})
                return
            settings = get_settings()
            if not owner_source_permitted(scope, settings):
                await send({"type": "websocket.close", "code": 4403})
                return
            scope.setdefault("state", {})["ops_owner_sub"] = subject
        await self.app(scope, receive, send)
