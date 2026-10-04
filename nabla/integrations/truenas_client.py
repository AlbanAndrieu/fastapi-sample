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
_HEALTH_CALL_TIMEOUT_SEC = 2.0
_APP_HEALTH_SELECT = [
    "id",
    "name",
    "state",
    "upgrade_available",
    "active_workloads.container_details.service_name",
    "active_workloads.container_details.image",
    "active_workloads.container_details.state",
]
logger = logging.getLogger(__name__)
_TALOS_VM_NAMES = ("taloscp01", "taloswk01", "taloswk02")


def _talos_vm_snapshot(vms: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize only the expected Talos VM runtime without exposing VM config."""
    by_name = {
        str(vm.get("name") or ""): vm
        for vm in vms
        if isinstance(vm, dict) and str(vm.get("name") or "") in _TALOS_VM_NAMES
    }
    rows: list[dict[str, str]] = []
    running = 0
    for name in _TALOS_VM_NAMES:
        vm = by_name.get(name)
        status = vm.get("status") if isinstance(vm, dict) else None
        state = str(status.get("state") or "MISSING") if isinstance(status, dict) else "MISSING"
        if state.upper() == "RUNNING":
            running += 1
        rows.append({"name": name, "state": state})
    healthy = running == len(_TALOS_VM_NAMES)
    return {
        "reachable": healthy,
        "state": "ok" if healthy else "fail",
        "probe": "truenas_vm_query",
        "evidence": "vm_runtime",
        "expected_vms": len(_TALOS_VM_NAMES),
        "running_vms": running,
        "vms": rows,
    }


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
        """Load the canonical FastAPI TrueNAS observer credential pair."""
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
        os.getenv("https_proxy", "").strip() or os.getenv("HTTPS_PROXY", "").strip(),
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
        for marker in (
            "you are not allowed to access this resource",
            "policy violation",
        )
    ):
        return "source_allowlist"
    if any(marker in message for marker in ("unauthorized", "authentication", "invalid credentials", "api key")):
        return "authentication"
    if "websocket" in message or any("websocket" in name for name in class_names):
        return "websocket"
    return "api"


def _rpc_failure_stage(exc: BaseException) -> str:
    """Classify an error after WebSocket authentication has already succeeded."""
    stage = _truenas_failure_stage(exc)
    if stage == "source_allowlist":
        return "access_denied"
    if stage == "connect_timeout":
        return "api_call_timeout"
    return stage


def _load_client_factory() -> Any:
    """Load the official client lazily, without adding startup work."""
    try:
        module = importlib.import_module("truenas_api_client")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "TrueNAS credentials are configured but truenas_api_client is not installed",
        ) from exc
    return module.Client


class TrueNASHealthProbeError(RuntimeError):
    """Preserve the failing TrueNAS health phase without exposing credentials."""

    def __init__(
        self,
        *,
        phase: str,
        stage: str,
        cause: BaseException,
        method: str,
        authenticated: bool,
        phase_elapsed_ms: int | None = None,
        call_timeout_seconds: float | None = None,
    ) -> None:
        super().__init__(str(cause).strip() or cause.__class__.__name__)
        self.phase = phase
        self.stage = stage
        self.method = method
        self.authenticated = authenticated
        self.exception_type = cause.__class__.__name__
        self.phase_elapsed_ms = phase_elapsed_ms
        self.call_timeout_seconds = call_timeout_seconds


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

    def _connect(
        self,
        *,
        call_timeout: float | None = None,
    ) -> TrueNASClientProtocol:
        return self._client_factory(
            uri=self.settings.websocket_uri,
            call_timeout=(
                self.settings.call_timeout
                if call_timeout is None
                else call_timeout
            ),
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
        result = self._call("app.query", [], {"select": _APP_HEALTH_SELECT})
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
        authenticated = False
        readiness_state = "unknown"
        readiness_error_type: str | None = None
        readiness_failure_stage: str | None = None
        readiness_elapsed_ms: int | None = None
        system_ready: bool | None = None
        system_state: str | None = None
        system_version_state = "ok"
        system_version_error_type: str | None = None
        system_version_failure_stage: str | None = None
        version: str | None = None
        app_inventory_state = "ok"
        app_inventory_error_type: str | None = None
        app_inventory_failure_stage: str | None = None
        apps: list[dict[str, Any]] = []
        vms: list[dict[str, Any]] | None = None
        vm_error_type: str | None = None
        vm_skip_reason: str | None = None
        websocket_elapsed_ms: int | None = None
        authentication_elapsed_ms: int | None = None
        system_version_elapsed_ms: int | None = None
        app_query_elapsed_ms: int | None = None
        vm_query_elapsed_ms: int | None = None
        connect_started = time.perf_counter()
        phase_started = connect_started
        try:
            with self._connect(call_timeout=_HEALTH_CALL_TIMEOUT_SEC) as client:
                websocket_elapsed_ms = round(
                    (time.perf_counter() - connect_started) * 1000,
                )
                phase = "authentication"
                method = "auth.login_with_api_key"
                auth_started = time.perf_counter()
                phase_started = auth_started
                client.login_with_api_key(self.settings.username, self.settings.api_key)
                authentication_elapsed_ms = round(
                    (time.perf_counter() - auth_started) * 1000,
                )
                authenticated = True

                # system.ready is the canonical authenticated readiness proof.
                # system.version and inventory RPCs are enrichment and must not
                # invalidate proven API availability when they are slow.
                phase = "call"
                method = "system.ready"
                ready_started = time.perf_counter()
                phase_started = ready_started
                try:
                    ready_value = client.call(method)
                    readiness_elapsed_ms = round(
                        (time.perf_counter() - ready_started) * 1000,
                    )
                    if not isinstance(ready_value, bool):
                        raise RuntimeError(
                            "TrueNAS system.ready returned an unexpected payload",
                        )
                    system_ready = ready_value
                    readiness_state = "ok" if ready_value else "warn"
                except Exception as ready_exc:
                    readiness_elapsed_ms = round(
                        (time.perf_counter() - ready_started) * 1000,
                    )
                    readiness_state = "warn"
                    readiness_error_type = ready_exc.__class__.__name__
                    readiness_failure_stage = _rpc_failure_stage(ready_exc)
                    logger.warning(
                        "TrueNAS readiness RPC unavailable uri=%s stage=%s exception=%s",
                        uri,
                        readiness_failure_stage,
                        readiness_error_type,
                    )

                if system_ready is False:
                    method = "system.state"
                    state_started = time.perf_counter()
                    phase_started = state_started
                    try:
                        state_value = client.call(method)
                        if isinstance(state_value, str):
                            system_state = state_value
                    except Exception as state_exc:
                        logger.warning(
                            "TrueNAS system state unavailable uri=%s stage=%s exception=%s",
                            uri,
                            _rpc_failure_stage(state_exc),
                            state_exc.__class__.__name__,
                        )

                method = "system.version"
                system_started = time.perf_counter()
                phase_started = system_started
                try:
                    version_value = client.call(method)
                    system_version_elapsed_ms = round(
                        (time.perf_counter() - system_started) * 1000,
                    )
                    if not isinstance(version_value, str):
                        raise RuntimeError(
                            "TrueNAS system.version returned an unexpected payload",
                        )
                    version = version_value
                except Exception as version_exc:
                    system_version_elapsed_ms = round(
                        (time.perf_counter() - system_started) * 1000,
                    )
                    system_version_state = "warn"
                    system_version_error_type = version_exc.__class__.__name__
                    system_version_failure_stage = _rpc_failure_stage(version_exc)
                    logger.warning(
                        "TrueNAS version enrichment unavailable uri=%s stage=%s exception=%s",
                        uri,
                        system_version_failure_stage,
                        system_version_error_type,
                    )
                    if system_ready is None:
                        raise

                version_timed_out = system_version_failure_stage == "api_call_timeout"
                if version_timed_out:
                    app_inventory_state = "warn"
                    app_inventory_error_type = "DeferredAfterRpcTimeout"
                    app_inventory_failure_stage = "deferred_after_timeout"
                else:
                    method = "app.query"
                    app_started = time.perf_counter()
                    phase_started = app_started
                    try:
                        apps = client.call(
                            method,
                            [],
                            {"select": _APP_HEALTH_SELECT},
                        )
                        app_query_elapsed_ms = round(
                            (time.perf_counter() - app_started) * 1000,
                        )
                    except Exception as app_exc:
                        app_query_elapsed_ms = round(
                            (time.perf_counter() - app_started) * 1000,
                        )
                        apps = []
                        app_inventory_state = "warn"
                        app_inventory_error_type = app_exc.__class__.__name__
                        app_inventory_failure_stage = _rpc_failure_stage(app_exc)
                        logger.warning(
                            "TrueNAS optional app inventory unavailable uri=%s stage=%s exception=%s",
                            uri,
                            app_inventory_failure_stage,
                            app_inventory_error_type,
                        )

                prior_rpc_timeout = "api_call_timeout" in {
                    readiness_failure_stage,
                    system_version_failure_stage,
                    app_inventory_failure_stage,
                }
                if prior_rpc_timeout:
                    vm_skip_reason = (
                        "TrueNAS vm.query deferred after an earlier RPC timeout "
                        "to preserve the aggregate health-probe budget"
                    )
                else:
                    method = "vm.query"
                    vm_started = time.perf_counter()
                    phase_started = vm_started
                    try:
                        vms = client.call(
                            method,
                            [],
                            {
                                "select": [
                                    "name",
                                    "status.state",
                                ],
                            },
                        )
                        vm_query_elapsed_ms = round(
                            (time.perf_counter() - vm_started) * 1000,
                        )
                    except Exception as vm_exc:
                        vm_query_elapsed_ms = round(
                            (time.perf_counter() - vm_started) * 1000,
                        )
                        # VM_READ is deliberately optional during the RBAC rollout.
                        # A missing VM capability must not invalidate proven TrueNAS
                        # liveness or the application inventory.
                        vms = None
                        vm_error_type = vm_exc.__class__.__name__
                        logger.warning(
                            "TrueNAS optional Talos VM observation unavailable uri=%s exception=%s",
                            uri,
                            vm_error_type,
                        )
        except Exception as exc:
            failed_at = time.perf_counter()
            elapsed_ms = round((failed_at - started) * 1000)
            phase_elapsed_ms = round((failed_at - phase_started) * 1000)
            failure_stage = _truenas_failure_stage(exc)
            if phase == "call" and failure_stage == "source_allowlist":
                failure_stage = "access_denied"
            elif phase == "call" and failure_stage == "connect_timeout":
                failure_stage = "api_call_timeout"
            logger.warning(
                "TrueNAS API health probe failed method=%s uri=%s verify_ssl=%s proxy_route=%s phase=%s stage=%s exception=%s elapsed_ms=%s error=%s",
                method,
                uri,
                self.settings.verify_ssl,
                proxy_route,
                phase,
                failure_stage,
                exc.__class__.__name__,
                elapsed_ms,
                str(exc)[:500],
            )
            raise TrueNASHealthProbeError(
                phase=phase,
                stage=failure_stage,
                cause=exc,
                method=method,
                authenticated=authenticated,
                phase_elapsed_ms=phase_elapsed_ms,
                call_timeout_seconds=_HEALTH_CALL_TIMEOUT_SEC,
            ) from exc
        logger.info(
            "TrueNAS API health probe succeeded uri=%s verify_ssl=%s proxy_route=%s elapsed_ms=%s",
            uri,
            self.settings.verify_ssl,
            proxy_route,
            round((time.perf_counter() - started) * 1000),
        )
        if version is not None and not isinstance(version, str):
            raise RuntimeError("TrueNAS system.version returned an unexpected health payload")
        if not isinstance(apps, list):
            raise RuntimeError("TrueNAS app.query returned an unexpected health payload")

        app_rows: list[dict[str, Any]] = []
        for app in apps:
            if not isinstance(app, dict):
                continue
            app_id = str(app.get("id") or app.get("name") or "unknown")
            row: dict[str, Any] = {
                "id": app_id,
                "name": str(app.get("name") or app_id),
                "state": str(app.get("state") or "UNKNOWN"),
                "upgrade_available": bool(app.get("upgrade_available", False)),
            }
            workloads = app.get("active_workloads")
            if isinstance(workloads, dict):
                containers = workloads.get("container_details")
                if isinstance(containers, list):
                    sanitized = [
                        {key: str(container[key]) for key in ("service_name", "image", "state") if container.get(key) is not None}
                        for container in containers
                        if isinstance(container, dict)
                    ]
                    if sanitized:
                        row["active_workloads"] = {"container_details": sanitized}
            app_rows.append(row)
        if isinstance(vms, list):
            talos = _talos_vm_snapshot([item for item in vms if isinstance(item, dict)])
        else:
            talos = {
                "reachable": None,
                "state": "unknown",
                "skipped": True,
                "reason": (
                    vm_skip_reason
                    or "TrueNAS vm.query unavailable; VM_READ is required"
                ),
                "probe": "truenas_vm_query",
                "evidence": "vm_runtime",
                "error_type": vm_error_type,
            }
        result: dict[str, Any] = {
            "reachable": True,
            "authenticated": True,
            "version": version,
            "system_ready": system_ready,
            "system_state": system_state,
            "readiness": {
                "state": readiness_state,
                "ready": system_ready,
                "system_state": system_state,
                "error_type": readiness_error_type,
                "failure_stage": readiness_failure_stage,
                "elapsed_ms": readiness_elapsed_ms,
            },
            "system_version": {
                "state": system_version_state,
                "available": version is not None,
                "error_type": system_version_error_type,
                "failure_stage": system_version_failure_stage,
                "elapsed_ms": system_version_elapsed_ms,
            },
            "websocket_elapsed_ms": websocket_elapsed_ms,
            "authentication_elapsed_ms": authentication_elapsed_ms,
            "api_elapsed_ms": system_version_elapsed_ms,
            "system_version_elapsed_ms": system_version_elapsed_ms,
            "health_call_timeout_seconds": _HEALTH_CALL_TIMEOUT_SEC,
            "app_inventory": {
                "state": app_inventory_state,
                "available": app_inventory_state == "ok",
                "error_type": app_inventory_error_type,
                "failure_stage": app_inventory_failure_stage,
                "elapsed_ms": app_query_elapsed_ms,
            },
            "talos": {
                **talos,
                "elapsed_ms": vm_query_elapsed_ms,
            },
        }
        if app_inventory_state == "ok":
            result["apps"] = app_rows
        return result


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
