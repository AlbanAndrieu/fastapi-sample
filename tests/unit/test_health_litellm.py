"""Tests for LiteLLM entry in /healthz checks."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from nabla.api import health_checks as hc


def test_probe_litellm_public_proxy_skipped_when_url_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = SimpleNamespace(litellm_healthz_url="   ")
    monkeypatch.setattr(hc, "get_settings", lambda: fake)
    out = hc.probe_litellm_public_proxy()
    assert out.get("skipped") is True
    assert out.get("reachable") is None


def test_probe_litellm_public_proxy_success_on_liveliness(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = SimpleNamespace(litellm_healthz_url="https://litellm.albandrieu.com")
    monkeypatch.setattr(hc, "get_settings", lambda: fake)

    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.status_code = 200

    mock_client = MagicMock()
    mock_client.get.return_value = mock_response
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_client
    mock_cm.__exit__.return_value = None

    with patch("nabla.api.health_checks.httpx.Client", return_value=mock_cm):
        out = hc.probe_litellm_public_proxy()

    assert out["reachable"] is True
    assert out["path"] == "/health/liveliness"
    assert "health/liveliness" in out["url"]
    mock_client.get.assert_called_once()
