"""Pyroscope health-board probe contracts."""

from collections.abc import Iterator
from contextlib import AbstractContextManager
from types import TracebackType
from typing import Any

from nabla.api import integration_health


class _Response:
    def __init__(self, status_code: int, text: str = "ok") -> None:
        self.status_code = status_code
        self.text = text

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300


class _FakeClient(AbstractContextManager["_FakeClient"]):
    def __init__(self, responses: Iterator[_Response], **_: Any) -> None:
        self._responses = responses

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def get(self, _url: str) -> _Response:
        return next(self._responses)


def _install_client(monkeypatch: Any, *responses: _Response) -> None:
    response_iter = iter(responses)
    monkeypatch.setattr(
        integration_health.httpx,
        "Client",
        lambda **kwargs: _FakeClient(response_iter, **kwargs),
    )
    monkeypatch.setattr(integration_health, "PYROSCOPE_ENABLED", True)
    monkeypatch.setattr(
        integration_health,
        "PYROSCOPE_ENDPOINT",
        "http://172.17.0.24:4040",
    )


def test_pyroscope_uses_root_for_health_and_metrics_for_prometheus(monkeypatch: Any) -> None:
    _install_client(monkeypatch, _Response(200, "Pyroscope"), _Response(200, "metric 1\n"))

    result = integration_health.probe_pyroscope_server()

    assert result["reachable"] is True
    assert result["path"] == "/"
    assert result["url"] == "http://172.17.0.24:4040/"
    assert result["metrics_url"] == "http://172.17.0.24:4040/metrics"
    assert result["metric_source"] == "prometheus"
    assert result["metrics_available"] is True
    assert result["metrics_http_status"] == 200


def test_pyroscope_root_404_is_not_reported_reachable(monkeypatch: Any) -> None:
    _install_client(monkeypatch, _Response(404, "not found"))

    result = integration_health.probe_pyroscope_server()

    assert result["reachable"] is False
    assert result["http_status"] == 404
    assert result["path"] == "/"
    assert "metrics_available" not in result


def test_pyroscope_metrics_failure_does_not_mark_service_down(monkeypatch: Any) -> None:
    _install_client(monkeypatch, _Response(200, "Pyroscope"), _Response(404, "not found"))

    result = integration_health.probe_pyroscope_server()

    assert result["reachable"] is True
    assert result["metrics_available"] is False
    assert result["metrics_http_status"] == 404
    assert "metrics_error" in result
