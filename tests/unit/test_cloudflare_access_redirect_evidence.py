"""Regression contracts for Cloudflare Access redirect and sticky-filter evidence."""

from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from nabla.api import homelab_health
from nabla.api.homelab_models import HomelabService
from nabla.api.sickz_cloudflare_edge import _probe_http_edge_evidence

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "nabla" / "api" / "assets"


def _configure_service_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "test.access")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "test-secret")


@pytest.mark.asyncio
async def test_access_redirect_keeps_initial_final_and_blocked_auth_separate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_service_token(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "example.cloudflareaccess.com":
            return httpx.Response(200, request=request, text="login")
        if request.headers.get("CF-Access-Client-Id"):
            return httpx.Response(
                302,
                request=request,
                headers={
                    "server": "cloudflare",
                    "cf-ray": "auth-blocked",
                    "location": "https://example.cloudflareaccess.com/cdn-cgi/access/login",
                },
            )
        return httpx.Response(
            302,
            request=request,
            headers={
                "server": "cloudflare",
                "cf-ray": "anonymous-blocked",
                "location": "https://example.cloudflareaccess.com/cdn-cgi/access/login",
            },
        )

    evidence = await _probe_http_edge_evidence(
        "https://karakeep.albandrieu.com/",
        transport=httpx.MockTransport(handler),
    )

    assert evidence["anonymous_initial_http_status"] == 302
    assert evidence["anonymous_final_http_status"] == 200
    assert evidence["authenticated_http_status"] == 302
    assert evidence["cloudflare_service_token_access_passed"] is False
    assert evidence["origin_reached"] is False


@pytest.mark.asyncio
async def test_origin_redirect_after_service_auth_counts_as_origin_reached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_service_token(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "example.cloudflareaccess.com":
            return httpx.Response(200, request=request, text="login")
        if request.headers.get("CF-Access-Client-Id"):
            return httpx.Response(
                307,
                request=request,
                headers={
                    "server": "cloudflare",
                    "cf-ray": "origin-redirect",
                    "location": "/sign-in",
                },
            )
        return httpx.Response(
            302,
            request=request,
            headers={
                "server": "cloudflare",
                "cf-ray": "anonymous-blocked",
                "location": "https://example.cloudflareaccess.com/cdn-cgi/access/login",
            },
        )

    evidence = await _probe_http_edge_evidence(
        "https://karakeep.albandrieu.com/",
        transport=httpx.MockTransport(handler),
    )

    assert evidence["anonymous_initial_http_status"] == 302
    assert evidence["anonymous_final_http_status"] == 200
    assert evidence["authenticated_http_status"] == 307
    assert evidence["cloudflare_service_token_access_passed"] is True
    assert evidence["origin_reached"] is True


@pytest.mark.asyncio
async def test_homelab_health_reprobes_access_redirect_with_service_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, request=request)

    edge_probe = AsyncMock(
        return_value={
            "cloudflare_http_evidence": True,
            "cloudflare_access_signal": True,
            "cloudflare_default_deny": False,
            "http_evidence_status": 302,
            "anonymous_initial_http_status": 302,
            "anonymous_final_http_status": 200,
            "authenticated_http_status": 307,
            "cloudflare_service_auth_attempted": True,
            "cloudflare_service_token_access_passed": True,
            "cloudflare_service_token_http_status": 307,
            "origin_reached": True,
        },
    )
    monkeypatch.setattr(homelab_health, "_probe_http_edge_evidence", edge_probe)
    service = HomelabService(
        id="karakeep",
        name="Karakeep",
        tunnelUrl="https://karakeep.albandrieu.com",
        tunnelSecure=True,
        external=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as client:
        result = await homelab_health._probe_public_service(
            client,
            __import__("asyncio").Semaphore(1),
            service,
        )

    edge_probe.assert_awaited_once_with("https://karakeep.albandrieu.com/")
    assert result["anonymous_http_status"] == 302
    assert result["anonymous_initial_http_status"] == 302
    assert result["anonymous_final_http_status"] == 200
    assert result["authenticated_http_status"] == 307
    assert result["http_status"] == 307
    assert result["public_probe_auth_mode"] == "cloudflare_service_token"
    assert result["origin_reached"] is True
    assert result["state"] == "ok"


def test_service_filter_sticky_mode_avoids_default_nested_scroll() -> None:
    javascript = (ASSETS / "api-global-service-filter.js").read_text(encoding="utf-8")
    stylesheet = (ASSETS / "api-service-diagnostics.css").read_text(encoding="utf-8")

    assert "STICKY_HYSTERESIS_PX" in javascript
    assert 'window.addEventListener("scroll", refreshSticky' in javascript
    assert "new IntersectionObserver(" not in javascript
    assert 'host.dataset.userCompact = "false";' in javascript
    assert 'button.textContent = compact ? "More filters" : "Compact filters";' in javascript
    assert "max-height: none;" in stylesheet
    assert "overflow: visible;" in stylesheet
    assert '.service-filter--global[data-stuck="true"][data-expanded="true"]' in stylesheet
    assert "overflow: auto;" in stylesheet
    assert ".service-filter--compact .service-filter-health-summary" in stylesheet


def test_operator_ui_exposes_redirect_chain_and_refresh_evidence_label() -> None:
    details = (ASSETS / "api-service-probe-details.js").read_text(encoding="utf-8")
    controller = (ASSETS / "api-health-controller.js").read_text(encoding="utf-8")

    for label in (
        "Anonymous initial HTTP",
        "Anonymous final HTTP",
        "Authenticated HTTP",
        "Origin reached",
        "Auth mode",
    ):
        assert label in details
    assert 'button.textContent = "↻ Refresh evidence";' in controller
