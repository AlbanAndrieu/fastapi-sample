"""Tests for LiteLLM entry in /healthz checks."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from nabla.api import integration_health as ih
from nabla.api.sickz_cloudflare_edge import cloudflare_edge_block


def test_probe_litellm_public_proxy_skipped_when_url_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = SimpleNamespace(litellm_healthz_url="   ")
    monkeypatch.setattr(ih, "get_settings", lambda: fake)
    out = ih.probe_litellm_public_proxy()
    assert out.get("skipped") is True
    assert out.get("reachable") is None


def test_probe_litellm_public_proxy_success_on_liveliness(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = SimpleNamespace(litellm_healthz_url="https://litellm.albandrieu.com")
    monkeypatch.setattr(ih, "get_settings", lambda: fake)

    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.status_code = 200

    mock_client = MagicMock()
    mock_client.get.return_value = mock_response
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_client
    mock_cm.__exit__.return_value = None

    with patch("nabla.api.integration_health.httpx.Client", return_value=mock_cm):
        out = ih.probe_litellm_public_proxy()

    assert out["reachable"] is True
    assert out["path"] == "/health/liveliness"
    assert "health/liveliness" in out["url"]
    mock_client.get.assert_called_once()


def _litellm_client(responses: list[MagicMock]) -> tuple[MagicMock, MagicMock]:
    mock_client = MagicMock()
    mock_client.get.side_effect = responses
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_client
    mock_cm.__exit__.return_value = None
    return mock_client, mock_cm


def _response(status: int, text: str = "", headers: dict[str, str] | None = None) -> MagicMock:
    response = MagicMock()
    response.is_success = 200 <= status < 300
    response.status_code = status
    response.text = text
    response.headers = headers or {}
    return response


def test_probe_litellm_cloudflare_challenge_is_unverified_not_down(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = SimpleNamespace(litellm_healthz_url="https://litellm.albandrieu.com")
    monkeypatch.setattr(ih, "get_settings", lambda: fake)
    challenge = _response(403, "<html><head><title>Just a moment...</title>", {"cf-mitigated": "challenge"})
    mock_client, mock_cm = _litellm_client([challenge])

    with patch("nabla.api.integration_health.httpx.Client", return_value=mock_cm):
        out = ih.probe_litellm_public_proxy()

    assert out["reachable"] is None
    assert out["edge_block"] == "challenge"
    assert out["path"] == "/health/liveliness"
    mock_client.get.assert_called_once()


def test_probe_litellm_plain_403_is_still_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = SimpleNamespace(litellm_healthz_url="https://litellm.albandrieu.com")
    monkeypatch.setattr(ih, "get_settings", lambda: fake)
    mock_client, mock_cm = _litellm_client([_response(403, "forbidden") for _ in range(3)])

    with patch("nabla.api.integration_health.httpx.Client", return_value=mock_cm):
        out = ih.probe_litellm_public_proxy()

    assert out == {"reachable": False, "error": "http_status=403", "base": "https://litellm.albandrieu.com"}
    assert mock_client.get.call_count == 3


@pytest.mark.parametrize("status", [200, 404, 500])
def test_cloudflare_challenge_markers_require_edge_block_status(status: int) -> None:
    assert cloudflare_edge_block(status, {"cf-mitigated": "challenge"}, "<title>Just a moment...</title>") is None


@pytest.mark.asyncio
async def test_enrich_integration_metadata_overlaps_tls_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = SimpleNamespace(litellm_healthz_url="https://litellm.example.test")
    monkeypatch.setattr(ih, "get_settings", lambda: fake)
    started: list[str] = []
    both_started = asyncio.Event()

    async def fake_tls(url: str) -> bool:
        started.append(url)
        if len(started) == 2:
            both_started.set()
        # A sequential implementation would never start the second probe.
        await asyncio.wait_for(both_started.wait(), timeout=1.0)
        return True

    monkeypatch.setattr(ih, "probe_https_tls_trusted", fake_tls)
    checks = {
        "litellm": {"reachable": True, "url": "https://litellm.example.test/health/liveliness"},
        "pyroscope": {"reachable": True, "url": "https://pyroscope.example.test"},
    }

    await ih.enrich_integration_metadata(checks)

    assert sorted(started) == [
        "https://litellm.example.test/health/liveliness",
        "https://pyroscope.example.test",
    ]
    assert checks["litellm"]["tls_trusted"] is True
    assert checks["litellm"]["display_label"] == "LiteLLM"
    assert checks["pyroscope"]["tls_trusted"] is True
    assert checks["pyroscope"]["href"] == "https://pyroscope.example.test"
