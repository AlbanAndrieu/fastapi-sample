"""Offline contracts for temporary public diagnostics and refresh isolation."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nabla.api import health_board, health_routes
from nabla.diagnostics_readonly_mode import public_diagnostics_readonly_enabled


@pytest.mark.parametrize(
    ("value", "enabled"),
    [
        ("true", True),
        (" TRUE ", True),
        ("on", True),
        ("1", True),
        ("yes", True),
        ("false", False),
        ("0", False),
        ("off", False),
        ("unexpected", False),
    ],
)
def test_temporary_readonly_switch(monkeypatch: pytest.MonkeyPatch, value: str, enabled: bool) -> None:
    monkeypatch.setenv("HOMELAB_PUBLIC_DIAGNOSTICS_READONLY", value)
    assert public_diagnostics_readonly_enabled() is enabled


@pytest.mark.parametrize(
    ("readonly", "authenticated", "expected_force"),
    [
        (True, False, False),
        (True, True, True),
        (False, False, True),
    ],
)
def test_anonymous_health_board_cannot_force_probe_refresh(
    monkeypatch: pytest.MonkeyPatch,
    readonly: bool,
    authenticated: bool,
    expected_force: bool,
) -> None:
    """Observe cached health without letting public readers start force refresh."""
    monkeypatch.setenv("HOMELAB_PUBLIC_DIAGNOSTICS_READONLY", "true" if readonly else "false")
    monkeypatch.setattr(health_routes, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(health_routes, "owner_ui_authenticated", lambda *_: authenticated)
    observed: list[bool] = []

    async def fake_snapshot(_request, *, force_refresh: bool = False) -> dict[str, bool]:
        observed.append(force_refresh)
        return {"force_refresh": force_refresh}

    monkeypatch.setattr(health_board, "get_health_board_snapshot", fake_snapshot)
    app = FastAPI()
    health_routes._register_health_board_routes(app)
    with TestClient(app) as client:
        response = client.get("/api/health-board?refresh=true")
    assert response.status_code == 200
    assert response.json() == {"force_refresh": expected_force}
    assert observed == [expected_force]
