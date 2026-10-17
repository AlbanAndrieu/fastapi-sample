"""Development reload stream: FastAPI SSE replaces the former arel WebSocket."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from nabla import dev_reload


def test_hot_reload_announces_boot_id_over_sse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dev_reload, "WATCHED_PATHS", ())
    app = FastAPI()
    app.include_router(dev_reload.router)

    response = TestClient(app).get("/hot-reload")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: boot\n" in response.text
    assert f'data: "{dev_reload.BOOT_ID}"' in response.text


def test_hot_reload_stays_out_of_openapi() -> None:
    app = FastAPI()
    app.include_router(dev_reload.router)

    assert "/hot-reload" not in app.openapi()["paths"]
