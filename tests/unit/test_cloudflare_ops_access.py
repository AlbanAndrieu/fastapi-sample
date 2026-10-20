"""Offline RS256 Cloudflare Access and WebSocket authorization tests."""

from __future__ import annotations

from types import SimpleNamespace
import time

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, WebSocket
from pydantic import SecretStr
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from nabla import access_control, asgi_transport_guard, cloudflare_ops_access as owner
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
