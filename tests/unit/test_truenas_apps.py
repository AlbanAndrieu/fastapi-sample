from __future__ import annotations

from nabla.integrations import truenas_api_ws


class FakeClient:
    def __init__(self, *args, **kwargs) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.login: tuple[str, str] | None = None

    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def login_with_api_key(self, username: str, api_key: str) -> None:
        self.login = (username, api_key)

    def call(self, method: str, *params: object) -> list[dict[str, object]]:
        self.calls.append((method, params))
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
    assert fake_client.login == ("dummy-user", "1-dummyapi1234567890")
    assert fake_client.calls == [("app.query", ())]


def test_compute_ws_url_accepts_http_and_existing_ws_paths(monkeypatch) -> None:
    monkeypatch.delenv("TRUENAS_WS_PATH", raising=False)

    assert truenas_api_ws.compute_ws_url("https://nas.test:7000") == ("wss://nas.test:7000/api/current")
    assert truenas_api_ws.compute_ws_url("wss://nas.test/api/current") == ("wss://nas.test/api/current")
