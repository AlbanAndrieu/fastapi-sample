"""Outside-in connection probes are bounded, fixed-target and fail closed."""

from __future__ import annotations

import httpx
import pytest

from nabla.api import external_connection_probes


@pytest.mark.asyncio
async def test_trusted_observer_checks_only_fixed_public_hosts() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        assert request.url.scheme == "https"
        if request.url.host == "fastapi-sample.fastapicloud.dev":
            assert request.url.path == "/api/ui/session"
            assert request.method == "GET"
            return httpx.Response(
                200,
                request=request,
                json={"authenticated": False, "readOnlyDiagnostics": True},
            )
        assert request.url.host == "cloudflare-dns.com"
        assert request.url.path == "/dns-query"
        assert request.url.params.get("name") in {
            "fastapi-sample.albandrieu.com",
            "fastapi-sample.fastapicloud.dev",
        }
        assert request.url.params.get("type") == "A"
        return httpx.Response(
            200,
            request=request,
            json={"Status": 0, "Answer": [{"type": 1, "data": "104.16.1.1"}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        value = await external_connection_probes.fetch_external_connection_probes(
            client=client,
            enabled=True,
        )
    assert len(seen) == 3
    assert value["cloud"]["state"] == "ok"
    assert value["cloud"]["origin_verified"] is True
    assert value["cloudflare_public_dns"]["fastapi-sample.albandrieu.com"]["state"] == "ok"
    assert value["dns_source"] == "cloudflare_recursive_doh_not_authoritative_zone"
    assert "104.16.1.1" not in str(value)


@pytest.mark.asyncio
async def test_cloudflare_access_is_not_a_healthy_cloud_origin() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "fastapi-sample.fastapicloud.dev":
            return httpx.Response(302, request=request, headers={"Location": "/cdn-cgi/access/login"})
        return httpx.Response(200, request=request, json={"Status": 3})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        value = await external_connection_probes.fetch_external_connection_probes(
            client=client,
            enabled=True,
        )
    assert value["cloud"]["category"] == "access_protected"
    assert value["cloud"]["origin_verified"] is False
    assert value["cloud"]["state"] != "ok"
    assert value["cloudflare_public_dns"]["fastapi-sample.albandrieu.com"]["category"] == "nxdomain"


@pytest.mark.asyncio
async def test_html_login_200_is_not_an_authenticated_api() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "fastapi-sample.fastapicloud.dev":
            return httpx.Response(
                200,
                request=request,
                headers={"Content-Type": "text/html"},
                text="<html>Access</html>",
            )
        return httpx.Response(200, request=request, json={"Status": 0, "Answer": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        value = await external_connection_probes.fetch_external_connection_probes(
            client=client,
            enabled=True,
        )
    assert value["cloud"]["state"] == "unknown"
    assert value["cloud"]["category"] == "unexpected_content"
    assert value["cloudflare_public_dns"]["fastapi-sample.albandrieu.com"]["state"] == "unknown"


@pytest.mark.asyncio
async def test_untrusted_runtime_never_contacts_public_endpoints(monkeypatch) -> None:
    monkeypatch.delenv("FASTAPI_RUNTIME_MODE", raising=False)
    result = await external_connection_probes.fetch_external_connection_probes()
    assert result["state"] == "not_executed"
    assert result["cloud"]["category"] == "not_executed"
    assert result["cloudflare_public_dns"] == {}


@pytest.mark.asyncio
async def test_transport_failure_does_not_claim_cloud_or_dns_outage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private network detail", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await external_connection_probes.fetch_external_connection_probes(
            client=client,
            enabled=True,
        )
    assert result["cloud"]["state"] == "unknown"
    assert all(item["state"] == "unknown" for item in result["cloudflare_public_dns"].values())
    assert "private network detail" not in str(result)
