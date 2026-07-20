from __future__ import annotations

import types

from nabla.integrations import truenas_api_ws


class FakeClient:
    def __init__(self, *args, **kwargs) -> None:
        self.calls: list[tuple[str, list[object]]] = []

    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def call(self, method: str, params: list[object] | None = None) -> list[dict[str, object]]:
        self.calls.append((method, params or []))
        if method == "auth.mechanism_choices":
            return ["API_KEY_PLAIN"]
        if method == "auth.login_ex":
            return {"response_type": "SUCCESS"}
        if method == "app.query":
            return [{"name": "vaultwarden", "id": "vaultwarden"}]
        raise AssertionError(f"unexpected method: {method}")


def test_fetch_truenas_apps_sync_uses_app_query(monkeypatch) -> None:
    fake_client = FakeClient()

    monkeypatch.setattr(truenas_api_ws, "Client", lambda *args, **kwargs: fake_client)
    monkeypatch.setattr(
        truenas_api_ws,
        "TRUENAS_API_KEY",
        "1-dummyapi1234567890",
    )
    monkeypatch.setattr(truenas_api_ws, "TRUENAS_USER", "dummy-user")
    monkeypatch.setattr(truenas_api_ws, "TRUENAS_WS_URL", "wss://example.test/api/current")

    releases = truenas_api_ws.fetch_truenas_apps_sync()

    assert releases == [{"name": "vaultwarden", "id": "vaultwarden"}]
    assert any(call[0] == "app.query" for call in fake_client.calls)
