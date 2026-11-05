"""Contract tests for the Tavily entry in /healthz checks."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from nabla.api import tavily_health as ih

_FAKE_KEY = "tvly-test-not-a-real-key"


def _patch_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> list[httpx.Request]:
    seen: list[httpx.Request] = []
    real_client = httpx.Client

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    def client_factory(**kwargs: object) -> httpx.Client:
        return real_client(transport=httpx.MockTransport(recording), **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(ih.httpx, "Client", client_factory)
    monkeypatch.setattr(ih, "tavily_api_key", lambda: _FAKE_KEY)
    return seen


def test_tavily_probe_skipped_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ih, "tavily_api_key", lambda: None)
    out = ih.probe_tavily_search()
    assert out == {"reachable": None, "skipped": True, "reason": "TAVILY_API_KEY not configured"}


def test_tavily_probe_uses_usage_endpoint_not_search(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _patch_transport(monkeypatch, lambda _r: httpx.Response(200, json={"key": {"usage": 1}}))

    out = ih.probe_tavily_search()

    assert out == {"reachable": True, "http_status": 200, "probe": "usage"}
    assert len(seen) == 1
    request = seen[0]
    assert request.method == "GET"
    assert str(request.url) == "https://api.tavily.com/usage"
    assert request.headers["Authorization"] == f"Bearer {_FAKE_KEY}"
    assert not request.content, "the probe must not send a search query body"


@pytest.mark.parametrize("status", [401, 403])
def test_tavily_probe_reports_rejected_key_as_authentication_failure(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
) -> None:
    _patch_transport(
        monkeypatch,
        lambda _r: httpx.Response(status, json={"detail": {"error": "Unauthorized: missing or invalid API key."}}),
    )

    out = ih.probe_tavily_search()

    assert out["reachable"] is False
    assert out["failure_stage"] == "authentication"
    assert out["http_status"] == status
    assert _FAKE_KEY not in json.dumps(out)


def test_tavily_probe_rate_limit_is_not_reported_as_outage(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_transport(monkeypatch, lambda _r: httpx.Response(429, headers={"Retry-After": "30"}))

    out = ih.probe_tavily_search()

    assert out["reachable"] is None
    assert out["failure_stage"] == "rate_limited"
    assert out["http_status"] == 429


def test_tavily_probe_server_error_is_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_transport(monkeypatch, lambda _r: httpx.Response(503))

    out = ih.probe_tavily_search()

    assert out == {"reachable": False, "error": "http_status=503", "http_status": 503, "probe": "usage"}


def test_tavily_probe_transport_error_does_not_leak_key(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _patch_transport(monkeypatch, boom)

    out = ih.probe_tavily_search()

    assert out["reachable"] is False
    assert out["probe"] == "usage"
    assert _FAKE_KEY not in json.dumps(out)
