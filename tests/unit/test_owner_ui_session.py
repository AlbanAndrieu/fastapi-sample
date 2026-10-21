"""Security regression for short-lived source-restricted diagnostics UI sessions."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from nabla import access_control
from nabla.api import owner_ui_session
from nabla.api.owner_ui_session import (
    COOKIE_NAME,
    SESSION_SECONDS,
    create_owner_cookie,
    owner_cookie_valid,
    register_owner_ui_session_routes,
)


def _settings():
    return SimpleNamespace(
        diagnostics_access_key=SecretStr("unit-only-secret-do-not-share"),
        admin_access_key=None,
        mcp_ops_key=None,
        ops_route_policy_strict=True,
        homelab_trusted_cidrs="82.66.4.247/32",
        homelab_trusted_proxy_cidrs="",
    )


def _client(monkeypatch, peer: str) -> TestClient:
    settings = _settings()
    monkeypatch.setattr(access_control, "get_settings", lambda: settings)
    monkeypatch.setattr(owner_ui_session, "get_settings", lambda: settings)
    app = FastAPI()
    app.middleware("http")(access_control.operations_access_middleware)
    register_owner_ui_session_routes(app)

    @app.get("/api/health-board")
    async def board():
        return {"secret_metric": "readable-to-owner-only"}

    @app.post("/api/health-board/cache/reset")
    async def reset():
        return {"reset": True}

    @app.get("/api/site/catalog/v2")
    async def site_catalog():
        return {"view": "service-only"}

    @app.get("/metrics")
    async def metrics():
        return {"private": True}

    return TestClient(app, base_url="https://fastapi-sample.fastapicloud.dev", client=(peer, 48399))


def _login(client: TestClient):
    return client.post(
        "/api/ui/session",
        headers={
            "Origin": "https://fastapi-sample.fastapicloud.dev",
            "X-Diagnostics-Key": "unit-only-secret-do-not-share",
        },
    )


def test_cookie_signature_expiry_tamper_and_key_rotation() -> None:
    settings = _settings()
    token = create_owner_cookie("unit-only-secret-do-not-share", now=1000)
    assert owner_cookie_valid(token, settings, now=1001)
    assert not owner_cookie_valid(token, settings, now=1000 + SESSION_SECONDS)
    assert not owner_cookie_valid(token + "0", settings, now=1001)
    assert not owner_cookie_valid(token[:-1] + "☠", settings, now=1001)
    assert not owner_cookie_valid("x" * 400, settings)
    settings.diagnostics_access_key = SecretStr("new-rotated-secret")
    assert not owner_cookie_valid(token, settings, now=1001)


def test_authorized_browser_session_can_read_health_but_not_other_scopes(monkeypatch) -> None:
    client = _client(monkeypatch, "82.66.4.247")
    assert client.get("/api/ui/session").json() == {"authenticated": False}
    assert client.get("/api/health-board").status_code == 401
    login = _login(client)
    assert login.status_code == 200
    cookie = login.headers["set-cookie"]
    assert COOKIE_NAME in cookie
    assert "httponly" in cookie.lower()
    assert "secure" in cookie.lower()
    assert "samesite=strict" in cookie.lower()
    assert client.get("/api/ui/session").json() == {"authenticated": True}
    assert client.get("/api/health-board").json()["secret_metric"] == "readable-to-owner-only"
    assert client.get("/metrics").status_code == 503
    assert client.get("/api/site/catalog/v2").status_code == 401
    assert client.post("/api/health-board/cache/reset").status_code == 403
    assert client.post(
        "/api/health-board/cache/reset",
        headers={"Origin": "https://fastapi-sample.fastapicloud.dev"},
    ).status_code == 200
    assert client.post(
        "/api/ui/session/logout",
        headers={"Origin": "https://fastapi-sample.fastapicloud.dev"},
    ).status_code == 200
    assert client.get("/api/health-board").status_code == 401


def test_cidr_and_origin_mandatory_even_with_correct_key(monkeypatch) -> None:
    remote = _client(monkeypatch, "203.0.113.42")
    assert _login(remote).status_code == 403
    assert remote.get("/api/health-board").status_code == 401
    local = _client(monkeypatch, "82.66.4.247")
    assert local.post("/api/ui/session", headers={
        "X-Diagnostics-Key": "unit-only-secret-do-not-share",
    }).status_code == 403
    assert local.post("/api/ui/session", headers={
        "Origin": "https://evil.example",
        "X-Diagnostics-Key": "unit-only-secret-do-not-share",
    }).status_code == 403
    assert local.post("/api/ui/session", headers={
        "Origin": "https://fastapi-sample.fastapicloud.dev",
        "X-Diagnostics-Key": "wrong",
    }).status_code == 401
    assert local.get(
        "/api/health-board",
        headers={"X-Forwarded-For": "82.66.4.247"},
    ).status_code == 401


def test_v1_http_retirement_flag_never_modifies_internal_probes(monkeypatch) -> None:
    from nabla.api.health_routes import _legacy_homelab_http_enabled

    monkeypatch.delenv("HOMELAB_V1_HTTP_ENABLED", raising=False)
    assert _legacy_homelab_http_enabled()
    monkeypatch.setenv("HOMELAB_V1_HTTP_ENABLED", "false")
    assert not _legacy_homelab_http_enabled()
    monkeypatch.setenv("HOMELAB_V1_HTTP_ENABLED", "unexpected")
    assert not _legacy_homelab_http_enabled()
