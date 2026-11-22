"""CrowdSec decisions: owner-only, LAN-only, key confined to a private LAPI, bounded DTO."""

from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nabla.api import crowdsec_decisions as cs
from nabla.route_policy import Visibility, route_policy_for

_PATH = "/api/homelab/crowdsec/decisions"
_KEY = "test-bouncer-key"


@pytest.fixture
def lan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cs, "homelab_runtime_detected", lambda: True)
    monkeypatch.setenv("CROWDSEC_OBSERVER_LAPI_KEY", _KEY)
    monkeypatch.delenv("CROWDSEC_LAPI_URL", raising=False)


def _transport(seen: list[httpx.Request], response: httpx.Response) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return response

    return httpx.MockTransport(handler)


def test_route_is_owner_only_and_rejects_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    owner = {"allowed": False}
    monkeypatch.setattr(cs, "owner_ui_authenticated", lambda *_: owner["allowed"])
    monkeypatch.setattr(cs, "homelab_runtime_detected", lambda: False)
    app = FastAPI()
    cs.register_crowdsec_decision_routes(app)
    client = TestClient(app)

    assert route_policy_for(_PATH).visibility is Visibility.OWNER
    assert client.get(_PATH).status_code == 403
    owner["allowed"] = True
    assert client.get(f"{_PATH}?value=1.2.3.4").status_code == 422
    response = client.get(_PATH)
    assert response.status_code == 200
    assert response.json()["state"] == "not_observed"
    assert response.headers["cache-control"].startswith("private, no-store")


@pytest.mark.asyncio
async def test_off_lan_and_unconfigured_never_call_the_lapi(monkeypatch: pytest.MonkeyPatch, lan: None) -> None:
    seen: list[httpx.Request] = []
    transport = _transport(seen, httpx.Response(200, json=[]))

    monkeypatch.setenv("CROWDSEC_LAPI_URL", "http://8.8.8.8:8084")
    assert (await cs.fetch_crowdsec_decisions(transport=transport))["state"] == "unconfigured"
    monkeypatch.setenv("CROWDSEC_LAPI_URL", "http://user@172.17.0.24:8084")
    assert (await cs.fetch_crowdsec_decisions(transport=transport))["state"] == "unconfigured"
    monkeypatch.delenv("CROWDSEC_LAPI_URL")
    monkeypatch.setenv("CROWDSEC_OBSERVER_LAPI_KEY", "")
    assert (await cs.fetch_crowdsec_decisions(transport=transport))["state"] == "unconfigured"
    monkeypatch.setattr(cs, "homelab_runtime_detected", lambda: False)
    assert (await cs.fetch_crowdsec_decisions(transport=transport))["state"] == "not_observed"
    assert seen == []


@pytest.mark.asyncio
async def test_local_decisions_are_validated_and_honeypot_first(lan: None) -> None:
    seen: list[httpx.Request] = []
    body = [
        {"value": "203.0.113.9", "type": "ban", "origin": "crowdsec", "scenario": "crowdsecurity/http-probing", "duration": "3h59m", "scope": "Ip"},
        {"value": "198.51.100.7", "type": "ban", "origin": "crowdsec", "scenario": "nabla/honeypot-login-burst", "duration": "3h", "scope": "Ip"},
        {"value": "FR", "type": "ban", "origin": "cscli", "scenario": "manual", "scope": "Country"},
        "not-a-decision",
    ]
    result = await cs.fetch_crowdsec_decisions(transport=_transport(seen, httpx.Response(200, json=body)))

    assert [str(r.url) for r in seen] == ["http://172.17.0.24:8084/v1/decisions?origins=crowdsec%2Ccscli"]
    assert seen[0].headers["X-Api-Key"] == _KEY
    assert (result["state"], result["count"], result["honeypot_count"]) == ("ok", 2, 1)
    assert [row["value"] for row in result["decisions"]] == ["198.51.100.7", "203.0.113.9"]
    assert result["decisions"][0]["honeypot"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (httpx.Response(200, content=b"null"), ("empty", "")),
        (httpx.Response(403, json={"message": "access forbidden"}), ("unavailable", "http_403")),
        (httpx.Response(200, json={"decisions": []}), ("unavailable", "unexpected_payload")),
        (httpx.Response(200, content=b"<html>"), ("unavailable", "invalid_json")),
    ],
)
async def test_failures_are_explicit_and_never_echo_the_key(lan: None, response: httpx.Response, expected: tuple[str, str]) -> None:
    result = await cs.fetch_crowdsec_decisions(transport=_transport([], response))

    assert (result["state"], result.get("reason", "")) == expected
    assert _KEY not in str(result)


def test_ui_loads_raw_ips_on_demand_and_escapes_them() -> None:
    assets = Path(cs.__file__).parent / "assets"
    javascript = (assets / "api-crowdsec-decisions.js").read_text(encoding="utf-8")
    truenas = (assets / "api-truenas.js").read_text(encoding="utf-8")

    assert 'panel.addEventListener("toggle"' in javascript
    assert "health-board-refreshed" not in javascript
    for field in ("value", "type", "scenario", "duration", "origin"):
        assert f"escapeText(row.{field})" in javascript
    # Mounted only once the owner-readable TrueNAS diagnostics snapshot renders.
    assert "renderIngressBlock(data, target);\n  installCrowdsecDecisions();" in truenas
