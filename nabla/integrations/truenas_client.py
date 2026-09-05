"""Read-only TrueNAS 26 adapter using the official WebSocket API client."""

from __future__ import annotations

import importlib
import logging
import os
import socket
import ssl
import time
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

from nabla.settings.homelab import (
    DEFAULT_TRUENAS_URL,
    DEFAULT_TRUENAS_WS_PATH,
    TrueNASProviderSettings,
)

_DEFAULT_API_PATH = DEFAULT_TRUENAS_WS_PATH
_DEFAULT_CALL_TIMEOUT_SEC = 5.0
logger = logging.getLogger(__name__)


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
    call_timeout: float = _DEFAULT_CALL_TIMEOUT_SEC

    @classmethod
    def from_environment(cls) -> TrueNASSettings | None:
        """Load optional TrueNAS credentials from the supported environment names."""
        environment = TrueNASProviderSettings()
        username = environment.adapter_username
        api_key = environment.adapter_api_key
        if not username or not api_key:
            return None

        return cls(
            url=environment.url,
            username=username,
            api_key=api_key,
            verify_ssl=environment.verify_ssl,
            websocket_path=environment.websocket_path,
        )

    @property
    def websocket_uri(self) -> str:
        """Normalize an HTTP(S) URL to the configured JSON-RPC WebSocket endpoint."""
        parsed = urlsplit(self.url)
        scheme = {
            "https": "wss",
            "http": "ws",
            "wss": "wss",
            "ws": "ws",
        }.get(parsed.scheme.lower())
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
    effective_url = TrueNASProviderSettings().url
    logger.debug("TrueNAS runtime endpoint: TRUENAS_URL=%s", effective_url)
    return effective_url


def truenas_host_port() -> tuple[str, int]:
    """Return the host and effective port derived from :envvar:`TRUENAS_URL`."""
    parsed = urlsplit(truenas_url())
    if parsed.scheme.lower() not in {"http", "https", "ws", "wss"} or not parsed.hostname:
        raise ValueError("TRUENAS_URL must be an HTTP(S) or WS(S) URL with a host")
    default_port = 443 if parsed.scheme.lower() in {"https", "wss"} else 80
    return parsed.hostname, parsed.port or default_port


def _no_proxy_matches(hostname: str) -> bool:
    """Mirror websocket-client domain NO_PROXY matching without exposing its value."""
    raw = os.getenv("no_proxy", os.getenv("NO_PROXY", "")).replace(" ", "")
    for entry in (item for item in raw.split(",") if item):
        if entry == "*" or hostname == entry:
            return True
        domain = entry.lstrip(".")
        if domain and (hostname == domain or hostname.endswith(f".{domain}")):
            return True
    return False


def _websocket_proxy_route(hostname: str | None) -> str:
    """Describe whether websocket-client can select an HTTPS proxy, without secrets."""
    if not hostname:
        return "unknown"
    if _no_proxy_matches(hostname):
        return "bypass"
    proxy_configured = bool(
        os.getenv("https_proxy", "").strip() or os.getenv("HTTPS_PROXY", "").strip()
    )
    return "proxy_candidate" if proxy_configured else "direct"


def _exception_chain(exc: BaseException) -> list[BaseException]:
    """Return a bounded cause/context chain for network error classification."""
    chain: list[BaseException] = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        chain.append(current)
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return chain


def _truenas_failure_stage(exc: BaseException) -> str:
    """Classify TrueNAS WebSocket/API failures for runtime diagnostics."""
    chain = _exception_chain(exc)
    message = " ".join(str(item) for item in chain).casefold()
    class_names = {item.__class__.__name__.casefold() for item in chain}

    if any(isinstance(item, socket.gaierror) for item in chain) or any(
        marker in message
        for marker in (
            "name or service not known",
            "temporary failure in name resolution",
            "getaddrinfo failed",
        )
    ):
        return "dns"
    if any(isinstance(item, ssl.SSLError) for item in chain) or any(
        marker in message
        for marker in (
            "certificate verify failed",
            "hostname mismatch",
            "ssl:",
            "tls",
        )
    ):
        return "tls"
    if any(isinstance(item, ConnectionResetError) for item in chain):
        return "connection_reset"
    if "connection refused" in message or "connectionrefusederror" in class_names:
        return "connect_refused"
    if "network is unreachable" in message or "no route to host" in message:
        return "network_unreachable"
    if "timeout" in message or any("timeout" in name for name in class_names):
        return "connect_timeout"
    if any(
        marker in message
        for marker in ("unauthorized", "authentication", "invalid credentials", "api key")
    ):
        return "authentication"
    if any("websocket" in name for name in class_names):
        return "websocket"
    return "api"


def _load_client_factory() -> Any:
    """Load the official client lazily, without adding startup work."""
    try:
        module = importlib.import_module("truenas_api_client")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "TrueNAS credentials are configured but truenas_api_client is not installed"
        ) from exc
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
            call_timeout=self.settings.call_timeout,
            verify_ssl=self.settings.verify_ssl,
        )

    def _call(self, method: str, *params: Any) -> Any:
        """Authenticate once for a single read-only JSON-RPC call."""
        started = time.perf_counter()
        uri = self.settings.websocket_uri
        proxy_route = _websocket_proxy_route(self.settings.hostname)
        phase = "connect"
        try:
            with self._connect() as client:
                phase = "authentication"
                client.login_with_api_key(self.settings.username, self.settings.api_key)
                phase = "call"
                result = client.call(method, *params)
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            logger.warning(
                "TrueNAS API probe failed method=%s uri=%s verify_ssl=%s proxy_route=%s phase=%s stage=%s exception=%s elapsed_ms=%s error=%s",
                method,
                uri,
                self.settings.verify_ssl,
                proxy_route,
                phase,
                _truenas_failure_stage(exc),
                exc.__class__.__name__,
                elapsed_ms,
                str(exc)[:500],
            )
            raise
        logger.debug(
            "TrueNAS API probe succeeded method=%s uri=%s verify_ssl=%s proxy_route=%s elapsed_ms=%s",
            method,
            uri,
            self.settings.verify_ssl,
            proxy_route,
            round((time.perf_counter() - started) * 1000),
        )
        return result

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
        started = time.perf_counter()
        uri = self.settings.websocket_uri
        proxy_route = _websocket_proxy_route(self.settings.hostname)
        phase = "connect"
        method = "connect"
        try:
            with self._connect() as client:
                phase = "authentication"
                method = "auth.login_with_api_key"
                client.login_with_api_key(self.settings.username, self.settings.api_key)
                phase = "call"
                method = "system.version"
                version = client.call(method)
                method = "app.query"
                apps = client.call(method)
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            logger.warning(
                "TrueNAS API health probe failed method=%s uri=%s verify_ssl=%s proxy_route=%s phase=%s stage=%s exception=%s elapsed_ms=%s error=%s",
                method,
                uri,
                self.settings.verify_ssl,
                proxy_route,
                phase,
                _truenas_failure_stage(exc),
                exc.__class__.__name__,
                elapsed_ms,
                str(exc)[:500],
            )
            raise
        logger.info(
            "TrueNAS API health probe succeeded uri=%s verify_ssl=%s proxy_route=%s elapsed_ms=%s",
            uri,
            self.settings.verify_ssl,
            proxy_route,
            round((time.perf_counter() - started) * 1000),
        )
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
