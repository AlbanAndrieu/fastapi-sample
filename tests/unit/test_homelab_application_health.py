"""Focused tests for homelab functional-health detection."""

import asyncio

import httpx
import pytest

from nabla.api import homelab_health
from nabla.api.homelab_health_evidence import build_reconciled_service_health
from nabla.api.homelab_models import HomelabService


@pytest.mark.asyncio
async def test_http_200_explicit_application_error_is_red() -> None:
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.method == "HEAD":
            return httpx.Response(
                200,
                headers={"content-type": "text/plain; charset=utf-8"},
                request=request,
            )
        return httpx.Response(
            200,
            text="Error: backend dictionary failed to initialize",
            headers={"content-type": "text/plain; charset=utf-8"},
            request=request,
        )

    service = HomelabService(
        name="Language Tool",
        tunnelUrl="https://languagetool.albandrieu.com",
        external=True,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await homelab_health._probe_public_service(
            client,
            asyncio.Semaphore(1),
            service,
        )

    assert methods == ["HEAD", "GET"]
    assert result["reachable"] is True
    assert result["http_status"] == 200
    assert result["state"] == "fail"
    assert result["application_error"].startswith("Error:")


@pytest.mark.asyncio
async def test_normal_html_200_stays_green() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                request=request,
            )
        return httpx.Response(
            200,
            text="<html><title>Service</title><body>Healthy service</body></html>",
            headers={"content-type": "text/html; charset=utf-8"},
            request=request,
        )

    service = HomelabService(
        name="Healthy service",
        tunnelUrl="https://healthy.albandrieu.com",
        external=True,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await homelab_health._probe_public_service(
            client,
            asyncio.Semaphore(1),
            service,
        )

    assert result["state"] == "ok"
    assert "application_error" not in result


def test_application_error_wins_over_running_internal_service() -> None:
    service = HomelabService(
        name="Language Tool",
        tunnelUrl="https://languagetool.albandrieu.com",
        internalHost="172.17.0.24",
        internalPort=8010,
        external=True,
    )
    public_result = {
        "id": service.service_id,
        "name": service.name,
        "url": "https://languagetool.albandrieu.com/",
        "reachable": True,
        "http_status": 200,
        "state": "fail",
        "tls_trusted": True,
        "application_error": "Error: service started but is not functional",
    }
    internal_result = {
        "id": service.service_id,
        "name": service.name,
        "host": "172.17.0.24",
        "port": 8010,
        "reachable": True,
        "state": "ok",
    }

    rows = build_reconciled_service_health(
        [service],
        public_results=[public_result],
        internal_results=[internal_result],
        runtime=None,
        tunnels=[],
    )

    assert rows[0]["state"] == "fail"
    assert rows[0]["application_error"] == public_result["application_error"]
