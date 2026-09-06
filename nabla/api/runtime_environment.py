"""Runtime-provider detection shared by UI and health diagnostics."""

from __future__ import annotations

import ipaddress
import os

_KNOWN_PAAS_ENV_MARKERS: tuple[str, ...] = (
    "VERCEL",
    "AWS_EXECUTION_ENV",
    "AWS_LAMBDA_FUNCTION_NAME",
    "KUBERNETES_SERVICE_HOST",
    "FLY_APP_NAME",
    "RAILWAY_ENVIRONMENT",
    "RAILWAY_PROJECT_ID",
    "HEROKU_APP_NAME",
    "DYNO",
)
_FASTAPI_CLOUD_ENV_MARKERS: tuple[str, ...] = (
    "FASTAPI_CLOUD",
    "FASTAPI_CLOUD_APP_ID",
)
_FASTAPI_CLOUD_NETWORK_LABELS = frozenset(
    {"fastapicloud", "fastapi-cloud", "fastapi_cloud"}
)
_LOCAL_FASTAPI_ENV_VALUES = frozenset(
    {"dev", "development", "local", "test", "testing"}
)
_LOCAL_HOSTNAMES = frozenset({"localhost", "localhost.localdomain"})
_HOMELAB_RUNTIME_MODE = "homelab"


def _env_present(name: str) -> bool:
    value = os.environ.get(name)
    return value is not None and str(value).strip() != ""


def _explicit_development_runtime() -> bool:
    return os.environ.get("FASTAPI_ENV", "").strip().casefold() in _LOCAL_FASTAPI_ENV_VALUES


def homelab_runtime_detected() -> bool:
    """Return whether this process is explicitly the trusted homelab runtime."""
    return (
        os.environ.get("FASTAPI_RUNTIME_MODE", "").strip().casefold()
        == _HOMELAB_RUNTIME_MODE
    )


def _explicit_local_hostname(hostname: str | None) -> bool:
    host = (hostname or "").strip().casefold().rstrip(".")
    if not host:
        return False
    if host in _LOCAL_HOSTNAMES:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_unspecified
    )


def fastapi_cloud_runtime_detected(hostname: str | None = None) -> bool:
    """Identify FastAPI Cloud while keeping explicit local requests local."""
    host = (hostname or "").strip().casefold().rstrip(".")
    if host.endswith(".fastapicloud.dev"):
        return True

    if homelab_runtime_detected():
        return False

    if _explicit_local_hostname(hostname) or _explicit_development_runtime():
        return False

    if any(_env_present(name) for name in _FASTAPI_CLOUD_ENV_MARKERS):
        return True

    network_label = os.environ.get("SICKZ_NETWORK_LABEL", "").strip().casefold()
    return network_label in _FASTAPI_CLOUD_NETWORK_LABELS


def known_paas_runtime_detected(hostname: str | None = None) -> bool:
    """Return whether a known cloud/PaaS runtime marker is present."""
    if _explicit_local_hostname(hostname) or _explicit_development_runtime():
        return False
    return fastapi_cloud_runtime_detected(hostname) or any(
        _env_present(name) for name in _KNOWN_PAAS_ENV_MARKERS
    )


def runtime_mode(hostname: str | None = None) -> str:
    """Return a stable scope for telemetry, UI and observer semantics."""
    host = (hostname or "").strip().casefold().rstrip(".")
    if host.endswith(".fastapicloud.dev"):
        return "fastapi_cloud"
    if homelab_runtime_detected():
        return "homelab"
    if fastapi_cloud_runtime_detected(hostname):
        return "fastapi_cloud"
    if known_paas_runtime_detected(hostname):
        return "cloud_paas"
    return "local"
