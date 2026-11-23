"""Offline RS256 Cloudflare Access and WebSocket authorization tests."""

from __future__ import annotations

from types import SimpleNamespace
import time

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, WebSocket
from pydantic import SecretStr
import pytest
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from nabla import access_control, asgi_transport_guard, cloudflare_ops_access as owner
from nabla.api import owner_ui_session
from nabla.asgi_transport_guard import OpsASGITransportGuard

ISSUER = "https://fixture.cloudflareaccess.com"
AUDIENCE = "fixture-ops-audience"
SUBJECT = "fixture-allowed-person"
SERVICE_CLIENT_ID = "service-123"


async def _fixture_keys(jwk):
    return [jwk]


@pytest.fixture
def identity(monkeypatch):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key(), as_dict=True)
    public.update({"kid": "fixture-kid", "alg": "RS256"})
    monkeypatch.setattr(owner, "signing_keys", lambda _issuer: _fixture_keys(public))
    settings = SimpleNamespace(
        ops_access_issuer=ISSUER,
        ops_access_aud=AUDIENCE,
        ops_access_owner_subjects=SUBJECT,
        ops_route_policy_strict=False,
        homelab_trusted_cidrs="82.66.4.247/32",
        diagnostics_access_key=SecretStr("machine-only-value"),
    )
    monkeypatch.setattr(owner, "get_settings", lambda: settings)
    monkeypatch.setattr(access_control, "get_settings", lambda: settings)
    monkeypatch.setattr(asgi_transport_guard, "get_settings", lambda: settings)

    def signed(**overrides):
        now = int(time.time())
        claims = {
            "iss": ISSUER,
            "aud": [AUDIENCE],
            "sub": SUBJECT,
            "type": "app",
            "iat": now - 1,
            "nbf": now - 1,
            "exp": now + 120,
        }
        claims.update(overrides)
        return jwt.encode(claims, private, algorithm="RS256", headers={"kid": "fixture-kid"})

    return settings, signed


@pytest.mark.asyncio
async def test_access_owner_negative_claims(identity):
    settings, signed = identity
    assert await owner.verify_owner_token(signed()) == SUBJECT
    other_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(
        {
            "iss": ISSUER,
            "aud": [AUDIENCE],
            "sub": SUBJECT,
            "type": "app",
            "iat": int(time.time()) - 1,
            "nbf": int(time.time()) - 1,
            "exp": int(time.time()) + 120,
        },
        other_private,
        algorithm="RS256",
        headers={"kid": "fixture-kid"},
    )
    for candidate in (
        forged,
        signed(aud=["other-application"]),
        signed(iss="https://other.cloudflareaccess.com"),
        signed(sub="someone-else"),
        signed(exp=int(time.time()) - 120),
        signed(sub="", common_name="machine-access-token"),
        signed(type="org"),
    ):
        with pytest.raises(owner.OwnerUnauthorized):
            await owner.verify_owner_token(candidate)
    settings.ops_access_owner_subjects = ""
    with pytest.raises(owner.OwnerConfigError):
        await owner.verify_owner_token(signed())


def test_owner_http_ignores_machine_header(identity):
    _settings, signed = identity
    app = FastAPI()
    app.middleware("http")(access_control.operations_access_middleware)

    @app.get("/private/ops/api/v1/summary")
    def summary():
        return {"ok": True}

    client = TestClient(app, client=("82.66.4.247", 53000))
    endpoint = "/private/ops/api/v1/summary"
    assert client.get(endpoint).status_code == 401
    assert client.get(endpoint, headers={"X-Diagnostics-Key": "machine-only-value"}).status_code == 401
    assert client.get(endpoint, headers={"Cf-Access-Jwt-Assertion": signed()}).status_code == 200
    denied = TestClient(app, client=("203.0.113.25", 53000))
    assert (
        denied.get(
            endpoint,
            headers={
                "Cf-Access-Jwt-Assertion": signed(),
                "CF-Connecting-IP": "82.66.4.247",
            },
        ).status_code
        == 403
    )
    _settings.homelab_trusted_cidrs = ""
    assert (
        client.get(
            endpoint,
            headers={"Cf-Access-Jwt-Assertion": signed()},
        ).status_code
        == 403
    )


def test_websockets_require_signed_owner(identity):
    _settings, signed = identity
    app = FastAPI()
    app.add_middleware(OpsASGITransportGuard)

    @app.websocket("/ws/sensor")
    async def sensor(ws: WebSocket):
        await ws.accept()
        await ws.send_text("connected")
        await ws.close()

    client = TestClient(app, client=("82.66.4.247", 53000))
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/sensor"):
            pass
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/sensor", headers={"X-Diagnostics-Key": "machine-only-value"}):
            pass
    with client.websocket_connect("/ws/sensor", headers={"Cf-Access-Jwt-Assertion": signed()}) as websocket:
        assert websocket.receive_text() == "connected"
    denied = TestClient(app, client=("203.0.113.25", 53000))
    with pytest.raises(WebSocketDisconnect):
        with denied.websocket_connect(
            "/ws/sensor",
            headers={
                "Cf-Access-Jwt-Assertion": signed(),
                "X-Forwarded-For": "82.66.4.247",
            },
        ):
            pass
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/unknown-websocket", headers={"Cf-Access-Jwt-Assertion": signed()}):
            pass


@pytest.mark.asyncio
async def test_access_issuer_must_be_cloudflare_tenant(monkeypatch):
    monkeypatch.setattr(
        owner,
        "get_settings",
        lambda: SimpleNamespace(
            ops_access_issuer="https://host.invalid",
            ops_access_aud=AUDIENCE,
            ops_access_owner_subjects=SUBJECT,
        ),
    )
    with pytest.raises(owner.OwnerConfigError):
        await owner.verify_owner_token("invalid")


def test_asgi_mounts_are_explicitly_owner_protected_even_before_strict(identity):
    settings, signed = identity
    settings.ops_route_policy_strict = False
    app = FastAPI()
    app.middleware("http")(access_control.operations_access_middleware)
    app.add_middleware(OpsASGITransportGuard, root_app=app)

    private = FastAPI()

    @private.get("/")
    def private_root():
        return {"private": True}

    unknown = FastAPI()

    @unknown.get("/")
    def unknown_root():
        return {"leak": True}

    app.mount("/a2a", private)
    app.mount("/unreviewed-asgi", unknown)
    client = TestClient(app, client=("82.66.4.247", 53000))

    assert client.get("/unreviewed-asgi/").status_code == 403
    assert client.get("/unreviewed-asgi/", headers={"Cf-Access-Jwt-Assertion": signed()}).status_code == 403
    assert client.get("/a2a/").status_code == 401
    assert client.get("/a2a/", headers={"X-Diagnostics-Key": "machine-only-value"}).status_code == 401
    assert client.get("/a2a/", headers={"Cf-Access-Jwt-Assertion": signed()}).status_code == 200
    denied = TestClient(app, client=("203.0.113.25", 53000))
    assert (
        denied.get(
            "/a2a/",
            headers={
                "Cf-Access-Jwt-Assertion": signed(),
                "CF-Connecting-IP": "82.66.4.247",
            },
        ).status_code
        == 403
    )


@pytest.mark.asyncio
async def test_owner_rejects_early_nbf_wrong_kid_and_service_token(identity):
    _, signed = identity
    now = int(time.time())
    for token in (
        signed(nbf=now + 600, exp=now + 720),
        signed(service_token_id=SERVICE_CLIENT_ID),
        signed(common_name="client.example"),
    ):
        with pytest.raises(owner.OwnerUnauthorized):
            await owner.verify_owner_token(token)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reply",
    [
        lambda request: httpx.Response(503),
        lambda request: httpx.Response(200, json={"keys": []}),
        lambda request: httpx.Response(200, json={"keys": [{"kty": "EC", "kid": "k"}]}),
        lambda request: httpx.Response(200, content=b"not json"),
    ],
    ids=["http-error", "empty", "no-rs256", "not-json"],
)
async def test_jwks_loss_is_unavailable_never_cached(monkeypatch, reply):
    real_client = httpx.AsyncClient
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return reply(request)

    monkeypatch.setattr(owner.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(owner, "_cache", {})
    for _ in range(2):
        with pytest.raises(owner.OwnerKeysUnavailable):
            await owner.signing_keys(ISSUER)
    # A failed fetch is retried on the next request, not served from cache.
    assert calls == [ISSUER + "/cdn-cgi/access/certs"] * 2


def test_jwks_loss_fails_closed_with_503(identity, monkeypatch):
    _settings, signed = identity

    async def unavailable(_issuer):
        raise owner.OwnerKeysUnavailable

    monkeypatch.setattr(owner, "signing_keys", unavailable)
    app = FastAPI()
    app.middleware("http")(access_control.operations_access_middleware)

    @app.get("/private/ops/api/v1/summary")
    def summary():
        return {"ok": True}

    client = TestClient(app, client=("82.66.4.247", 53000))
    response = client.get("/private/ops/api/v1/summary", headers={"Cf-Access-Jwt-Assertion": signed()})
    assert response.status_code == 503
    assert response.json() == {"detail": "Owner identity provider unavailable"}


def test_homelab_sso_owner_only_and_no_secondary_cookie(identity, monkeypatch):
    settings, signed = identity
    settings.homelab_owner_access_sso = True
    settings.ops_route_policy_strict = True
    monkeypatch.setenv("FASTAPI_RUNTIME_MODE", "homelab")
    monkeypatch.setattr(owner_ui_session, "get_settings", lambda: settings)
    app = FastAPI()
    app.middleware("http")(access_control.operations_access_middleware)
    owner_ui_session.register_owner_ui_session_routes(app)

    @app.get("/api/health-board")
    def board():
        return {"owner": True}

    @app.post("/api/health-board/cache/reset")
    def reset():
        return {"owner": True}

    @app.get("/api/site/catalog/v2")
    def service():
        return {"service": True}

    client = TestClient(app, base_url="https://fixture.example", client=("82.66.4.247", 53000))
    headers = {"Cf-Access-Jwt-Assertion": signed()}
    session = client.get("/api/ui/session", headers=headers)
    assert session.json() == {"authenticated": True, "provider": "cloudflare_access"}
    assert "set-cookie" not in session.headers
    assert client.get("/api/health-board", headers=headers).status_code == 200
    assert client.get("/api/health-board").status_code == 401
    assert client.get("/api/health-board", headers={"Cf-Access-Authenticated-User-Email": "owner@example.invalid"}).status_code == 401
    assert client.get("/api/health-board", headers={"Cf-Access-Jwt-Assertion": signed(sub="", common_name="monitor")}).status_code == 401
    assert client.get("/api/site/catalog/v2", headers=headers).status_code == 401
    assert client.post("/api/health-board/cache/reset", headers=headers).status_code == 403
    assert client.post("/api/health-board/cache/reset", headers={**headers, "Origin": "https://fixture.example", "Sec-Fetch-Site": "same-origin"}).status_code == 200
    monkeypatch.setenv("FASTAPI_RUNTIME_MODE", "fastapi_cloud")
    assert client.get("/api/health-board", headers=headers).status_code == 401
    monkeypatch.setenv("FASTAPI_RUNTIME_MODE", "homelab")
    settings.homelab_owner_access_sso = False
    assert client.get("/api/health-board", headers=headers).status_code == 401


_MCP_KEY = "mcp-fixture-key-0123456789abcdef"


def _mcp_a2a_app():
    app = FastAPI()
    app.middleware("http")(access_control.operations_access_middleware)

    class StreamableMcp:  # an ASGI app object like FastMCP.http_app(), not a GET endpoint
        async def __call__(self, scope, receive, send):
            await JSONResponse({"mcp": True})(scope, receive, send)

    # Same registration as app_factory: an exact Route, not a Mount.
    app.router.routes.append(Route("/mcp", StreamableMcp()))
    a2a = FastAPI()

    @a2a.get("/.well-known/agent-card.json")
    def agent_card():
        return {"name": "fixture"}

    app.mount("/a2a", a2a)

    @app.get("/v1/mcp/ops/servers")
    def mcp_ops_servers():
        return {"servers": []}

    return TestClient(OpsASGITransportGuard(app, root_app=app), client=("82.66.4.247", 53000))


@pytest.mark.parametrize("strict", [False, True], ids=["staged", "strict"])
def test_mcp_and_a2a_recette_before_strict_mode(identity, strict):
    """P2 sign-off: MCP needs its key, A2A a human owner, in both policy modes."""
    settings, signed = identity
    settings.ops_route_policy_strict = strict
    settings.mcp_ops_key = SecretStr(_MCP_KEY)
    client = _mcp_a2a_app()
    card = "/a2a/.well-known/agent-card.json"

    for headers in ({}, {"X-MCP-Key": "wrong"}, {"Cf-Access-Jwt-Assertion": signed()}, {"X-Diagnostics-Key": "machine-only-value"}):
        assert client.post("/mcp", headers=headers).status_code == 401
        assert client.get("/v1/mcp/ops/servers", headers=headers).status_code == 401
    assert client.post("/mcp", headers={"X-MCP-Key": _MCP_KEY}).json() == {"mcp": True}
    assert client.post("/mcp", headers={"Authorization": f"Bearer {_MCP_KEY}"}).status_code == 200
    assert client.get("/v1/mcp/ops/servers", headers={"X-MCP-Key": _MCP_KEY}).status_code == 200

    for token in (None, signed(aud=["another-audience"]), signed(service_token_id=SERVICE_CLIENT_ID)):
        headers = {"Cf-Access-Jwt-Assertion": token} if token else {}
        assert client.get(card, headers=headers).status_code == 401
    assert client.get(card, headers={"Cf-Access-Jwt-Assertion": signed()}).json() == {"name": "fixture"}

    for path in ("/mcp", "/a2a"):
        with pytest.raises(WebSocketDisconnect) as closed, client.websocket_connect(path, headers={"X-MCP-Key": _MCP_KEY}):
            pass
        assert closed.value.code == 4403


def test_mcp_ops_without_configured_key_fails_closed(identity):
    """Before 22/11 /v1/mcp/ops was REVIEW, hence anonymous outside strict mode."""
    settings, _signed = identity
    settings.mcp_ops_key = None
    assert _mcp_a2a_app().get("/v1/mcp/ops/servers").status_code == 503


def test_a2a_mount_jwks_loss_is_503_like_http_owner_routes(identity, monkeypatch):
    _settings, signed = identity

    async def unavailable(_issuer):
        raise owner.OwnerKeysUnavailable

    monkeypatch.setattr(owner, "signing_keys", unavailable)
    response = _mcp_a2a_app().get("/a2a/.well-known/agent-card.json", headers={"Cf-Access-Jwt-Assertion": signed()})
    assert response.status_code == 503
    assert response.json() == {"detail": "Owner identity provider unavailable"}
