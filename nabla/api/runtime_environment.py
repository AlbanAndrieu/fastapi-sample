"""Runtime-provider detection shared by UI and health diagnostics."""

from __future__ import annotations

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


def _env_present(name: str) -> bool:
    value = os.environ.get(name)
    return value is not None and str(value).strip() != ""


def fastapi_cloud_runtime_detected(hostname: str | None = None) -> bool:
    """Identify this project's FastAPI Cloud runtime without assuming one env var."""
    if any(_env_present(name) for name in _FASTAPI_CLOUD_ENV_MARKERS):
        return True

    network_label = os.environ.get("SICKZ_NETWORK_LABEL", "").strip().casefold()
    if network_label in _FASTAPI_CLOUD_NETWORK_LABELS:
        return True

    host = (hostname or "").strip().casefold().rstrip(".")
    return host.endswith(".fastapicloud.dev")


def known_paas_runtime_detected() -> bool:
    """Return whether a known cloud/PaaS runtime marker is present."""
    return fastapi_cloud_runtime_detected() or any(
        _env_present(name) for name in _KNOWN_PAAS_ENV_MARKERS
    )


def runtime_mode(hostname: str | None = None) -> str:
    """Return a stable scope for telemetry and UI semantics."""
    if fastapi_cloud_runtime_detected(hostname):
        return "fastapi_cloud"
    if known_paas_runtime_detected():
        return "cloud_paas"
    return "local"
