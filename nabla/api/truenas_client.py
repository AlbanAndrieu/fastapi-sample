"""Read-only TrueNAS 26 adapter using the official websocket API client."""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

_DEFAULT_TRUENAS_URL = "https://172.17.0.24"
_DEFAULT_API_PATH = "/api/current"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


class TrueNASClientProtocol(Protocol):
    """Subset of the official TrueNAS client used by this adapter."""

    def __enter__(self) -> TrueNASClientProtocol: ...

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...

    def login_with_api_key(self, username: str, api_key: str) -> Any: ...

    def call(self, method: str, *params: Any) -> Any: ...


@dataclass(frozen=True, slots=True)
class TrueNASSettings:
    """Configuration for read-only TrueNAS 26 JSON-RPC access."""

    url: str = _DEFAULT_TRUENAS_URL
    username: str = ""
    api_key: str = ""
    verify_ssl: bool = True

    @classmethod
    def from_environment(cls) -> TrueNASSettings | None:
        """Load credentials without making the API mandatory for normal runtime."""
        username = (
            os.getenv("TRUENAS_API_USERNAME", "").strip()
            or os.getenv("TRUENAS_USERNAME", "").strip()
        )
        api_key = (
            os.getenv("TRUENAS_API_KEY", "").strip()
            or os.getenv("TRUENAS_MCP_API_KEY", "").strip()
        )
        if not username or not api_key:
            return None
        verify_ssl = os.getenv("TRUENAS_API_VERIFY_SSL", "true").strip().lower() in _TRUE_VALUES
        return cls(
            url=os.getenv("TRUENAS_URL", _DEFAULT_TRUENAS_URL).strip()
            or _DEFAULT_TRUENAS_URL,
            username=username,
            api_key=api_key,
            verify_ssl=verify_ssl,
        )

    @property
    def websocket_uri(self) -> str:
        """Normalize an HTTP(S) TrueNAS URL to the v26 JSON-RPC websocket endpoint."""
        parsed = urlsplit(self.url)
        scheme = {"https": "wss", "http": "ws", "wss": "wss", "ws": "ws"}.get(
            parsed.scheme.lower()
        )
        if scheme is None or not parsed.netloc:
            raise ValueError("TRUENAS_URL must be an HTTP(S) or WS(S) URL with a host")
        path = parsed.path.rstrip("/")
        if not path or path == "/":
            path = _DEFAULT_API_PATH
        elif not path.endswith(_DEFAULT_API_PATH):
            path = f"{path}{_DEFAULT_API_PATH}"
        return urlunsplit((scheme, parsed.netloc, path, "", ""))


def _load_client_factory() -> Any:
    """Load the official client lazily so absent credentials add no startup cost."""
    try:
        module = importlib.import_module("truenas_api_client")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "TrueNAS API credentials are configured but the official "
            "truenas_api_client package is not installed"
        ) from exc
    return module.Client


class TrueNASReadOnlyAdapter:
    """Small synchronous adapter over the TrueNAS 26 official websocket client."""

    def __init__(
        self,
        settings: TrueNASSettings,
        *,
        client_factory: Any | None = None,
    ) -> None:
        self._settings = settings
        self._client_factory = client_factory or _load_client_factory()

    def _connect(self) -> TrueNASClientProtocol:
        return self._client_factory(
            uri=self._settings.websocket_uri,
            verify_ssl=self._settings.verify_ssl,
        )

    def system_info(self) -> dict[str, Any]:
        """Return sanitized system metadata after authenticated read-only access."""
        with self._connect() as client:
            client.login_with_api_key(self._settings.username, self._settings.api_key)
            result = client.call("system.info")
        if not isinstance(result, dict):
            raise RuntimeError("TrueNAS system.info returned an unexpected payload")
        return result

    def list_apps(self) -> list[dict[str, Any]]:
        """Return installed app inventory through the v26 ``app.query`` method."""
        with self._connect() as client:
            client.login_with_api_key(self._settings.username, self._settings.api_key)
            result = client.call("app.query")
        if not isinstance(result, list):
            raise RuntimeError("TrueNAS app.query returned an unexpected payload")
        return [item for item in result if isinstance(item, dict)]

    def health_snapshot(self) -> dict[str, Any]:
        """Return a small non-secret host/app status view suitable for health APIs."""
        with self._connect() as client:
            client.login_with_api_key(self._settings.username, self._settings.api_key)
            system = client.call("system.info")
            apps = client.call("app.query")
        if not isinstance(system, dict) or not isinstance(apps, list):
            raise RuntimeError("TrueNAS API returned an unexpected health payload")

        app_rows = [
            {
                "name": str(app.get("name") or app.get("id") or "unknown"),
                "state": str(app.get("state") or "UNKNOWN"),
                "upgrade_available": bool(app.get("upgrade_available", False)),
            }
            for app in apps
            if isinstance(app, dict)
        ]
        return {
            "reachable": True,
            "version": system.get("version"),
            "hostname": system.get("hostname"),
            "apps": app_rows,
        }


def observe_truenas_api() -> dict[str, Any] | None:
    """Read TrueNAS only when an explicit username + API key are configured."""
    settings = TrueNASSettings.from_environment()
    if settings is None:
        return None
    return TrueNASReadOnlyAdapter(settings).health_snapshot()
