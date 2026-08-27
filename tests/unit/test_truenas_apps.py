from __future__ import annotations

from unittest.mock import Mock

from nabla.integrations.truenas_apps import get_truenas_apps_json
from nabla.integrations.truenas_client import TrueNASReadOnlyAdapter, TrueNASSettings


class FakeClient:
    def __init__(self, *, uri: str, verify_ssl: bool) -> None:
        self.uri = uri
        self.verify_ssl = verify_ssl
        self.login = Mock()
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self) -> FakeClient:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def login_with_api_key(self, username: str, api_key: str) -> None:
        self.login(username, api_key)

    def call(self, method: str, *params: object) -> list[dict[str, object]]:
        self.calls.append((method, params))
        if method == "app.query":
            return [
                {
                    "name": "vaultwarden",
                    "id": "vaultwarden",
                    "state": "RUNNING",
                    "active_workloads": {"used_ports": [], "container_details": []},
                },
            ]
        raise AssertionError(f"unexpected method: {method}")


def test_get_truenas_apps_json_uses_shared_adapter() -> None:
    clients: list[FakeClient] = []

    def factory(**kwargs):
        client = FakeClient(**kwargs)
        clients.append(client)
        return client

    settings = TrueNASSettings(
        url="https://nas.test:7000",
        username="dummy-user",
        api_key="1-dummyapi1234567890",
        verify_ssl=False,
    )
    adapter = TrueNASReadOnlyAdapter(settings, client_factory=factory)

    payload = get_truenas_apps_json(adapter)

    assert payload["version"] == 2
    assert payload["services"][0]["name"] == "vaultwarden"
    assert payload["services"][0]["internalHost"] == "nas.test"
    assert clients[0].uri == "wss://nas.test:7000/api/current"
    assert clients[0].verify_ssl is False
    clients[0].login.assert_called_once_with("dummy-user", "1-dummyapi1234567890")
    assert clients[0].calls == [("app.query", ())]
