"""Read-only TrueNAS 26 adapter using the official WebSocket API client."""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

DEFAULT_TRUENAS_URL = "https://truenas.albandrieu.com:7000"
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

    url: str = DEFAULT_TRUENAS_URL
    username: str = ""
    api_key: str = ""
    verify_ssl: bool = True
    websocket_path: str = _DEFAULT_API_PATH

    @classmethod
    def from_environment(cls) -> TrueNASSettings | None:
        """Load optional TrueNAS credentials from the supported environment names."""
        username = os.getenv("TRUENAS_API_USERNAME", "").strip() or os.getenv("TRUENAS_USERNAME", "").strip() or os.getenv("TRUENAS_USER", "").strip()
        api_key = os.getenv("TRUENAS_API_KEY", "").strip() or os.getenv("TRUENAS_MCP_API_KEY", "").strip()
        if not username or not api_key:
            return None

        verify_ssl_raw = os.getenv("TRUENAS_API_VERIFY_SSL", "").strip() or os.getenv("TRUENAS_VERIFY_SSL", "true").strip()
        websocket_path = os.getenv("TRUENAS_WS_PATH", _DEFAULT_API_PATH).strip()
        return cls(
            url=truenas_url(),
            username=username,
            api_key=api_key,
            verify_ssl=verify_ssl_raw.lower() in _TRUE_VALUES,
            websocket_path=websocket_path or _DEFAULT_API_PATH,
        )

    @property
    def websocket_uri(self) -> str:
        """Normalize an HTTP(S) URL to the configured JSON-RPC WebSocket endpoint."""
        parsed = urlsplit(self.url)
        scheme = {"https": "wss", "http": "ws", "wss": "wss", "ws": "ws"}.get(parsed.scheme.lower())
        if scheme is None or not parsed.netloc:
            raise ValueError("TRUENAS_URL must be an HTTP(S) or WS(S) URL with a host")

        path = parsed.path.rstrip("/")
        configured_path = "/" + self.websocket_path.lstrip("/")
        if not path or path == "/":
            path = configured_path
        elif not path.endswith(configured_path):
            path = f"{path}{configured_path}"
        return urlunsplit((scheme, parsed.netloc, path, "", ""))

    @property
    def hostname(self) -> str | None:
        """Return the configured TrueNAS host without exposing credentials."""
        return urlsplit(self.url).hostname


def truenas_url() -> str:
    """Return the single configured TrueNAS endpoint used by every probe."""
    configured = os.getenv("TRUENAS_URL", DEFAULT_TRUENAS_URL).strip()
    return configured or DEFAULT_TRUENAS_URL


def truenas_host_port() -> tuple[str, int]:
    """Return the host and effective port derived from :envvar:`TRUENAS_URL`."""
    parsed = urlsplit(truenas_url())
    if parsed.scheme.lower() not in {"http", "https", "ws", "wss"} or not parsed.hostname:
        raise ValueError("TRUENAS_URL must be an HTTP(S) or WS(S) URL with a host")
    default_port = 443 if parsed.scheme.lower() in {"https", "wss"} else 80
    return parsed.hostname, parsed.port or default_port


def _load_client_factory() -> Any:
    """Load the official client lazily, without adding startup work."""
    try:
        module = importlib.import_module("truenas_api_client")
    except ModuleNotFoundError as exc:
        raise RuntimeError("TrueNAS credentials are configured but truenas_api_client is not installed") from exc
    return module.Client


class TrueNASReadOnlyAdapter:
    """Small synchronous adapter over the TrueNAS 26 official WebSocket client."""

    def __init__(
        self,
        settings: TrueNASSettings,
        *,
        client_factory: Any | None = None,
    ) -> None:
        self.settings = settings
        self._client_factory = client_factory or _load_client_factory()

    def _connect(self) -> TrueNASClientProtocol:
        return self._client_factory(
            uri=self.settings.websocket_uri,
            verify_ssl=self.settings.verify_ssl,
        )

    def _call(self, method: str, *params: Any) -> Any:
        """Authenticate once for a single read-only JSON-RPC call."""
        with self._connect() as client:
            client.login_with_api_key(self.settings.username, self.settings.api_key)
            return client.call(method, *params)

    def system_version(self) -> str:
        """Return the TrueNAS software version."""
        result = self._call("system.version")
        if not isinstance(result, str):
            raise RuntimeError("TrueNAS system.version returned an unexpected payload")
        return result

    def list_apps(self) -> list[dict[str, Any]]:
        """Return installed app inventory through the v26 ``app.query`` method."""
        result = self._call("app.query")
        if not isinstance(result, list):
            raise RuntimeError("TrueNAS app.query returned an unexpected payload")
        return [item for item in result if isinstance(item, dict)]

    def health_snapshot(self) -> dict[str, Any]:
        """Return a compact non-secret version/app view suitable for health APIs."""
        with self._connect() as client:
            client.login_with_api_key(self.settings.username, self.settings.api_key)
            version = client.call("system.version")
            apps = client.call("app.query")
        if not isinstance(version, str) or not isinstance(apps, list):
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
        return {"reachable": True, "version": version, "apps": app_rows}


def build_truenas_adapter() -> TrueNASReadOnlyAdapter | None:
    """Build the optional adapter from runtime configuration."""
    settings = TrueNASSettings.from_environment()
    if settings is None:
        return None
    return TrueNASReadOnlyAdapter(settings)


def observe_truenas_api() -> dict[str, Any] | None:
    """Read TrueNAS only when an explicit username + API key are configured."""
    adapter = build_truenas_adapter()
    return adapter.health_snapshot() if adapter is not None else None
