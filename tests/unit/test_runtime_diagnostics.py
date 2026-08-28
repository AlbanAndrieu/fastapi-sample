"""Security tests for local runtime diagnostic routes."""

from fastapi import HTTPException
import pytest
from starlette.requests import Request

from nabla.api.runtime_diagnostics import _require_loopback


def _request_from(client_host: str) -> Request:
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/v1/runtime/logs",
            "raw_path": b"/v1/runtime/logs",
            "query_string": b"",
            "headers": [],
            "client": (client_host, 12345),
            "server": ("127.0.0.1", 8080),
        }
    )


def test_runtime_diagnostics_accept_loopback() -> None:
    _require_loopback(_request_from("127.0.0.1"))
    _require_loopback(_request_from("::1"))


def test_runtime_diagnostics_reject_lan_client() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _require_loopback(_request_from("172.17.0.57"))

    assert exc_info.value.status_code == 403
