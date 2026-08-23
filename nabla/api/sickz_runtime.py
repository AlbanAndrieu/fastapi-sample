"""Runtime/network policy for inverse-reachability probes."""

from __future__ import annotations

import os
from typing import Any

from nabla.config_settings import APP_DOMAIN, APIDeploymentSettings


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


def _network_label(settings: APIDeploymentSettings) -> str:
    custom = (settings.sickz_network_label or "").strip()
    if custom:
        return custom
    return (APP_DOMAIN or "").strip() or "this deployment"


def _known_paas_runtime_detected() -> bool:
    env = os.environ
    return any(
        env.get(key) is not None and str(env.get(key)).strip() != ""
        for key in _KNOWN_PAAS_ENV_MARKERS
    )


def _implicit_internal_network(settings: APIDeploymentSettings) -> bool:
    if (settings.sickz_network_label or "").strip().lower() == "nabla":
        return True
    return (APP_DOMAIN or "").strip().lower() == "albandrieu.albandrieu.com"


def _internal_network_implicit(settings: APIDeploymentSettings) -> bool:
    if bool(settings.sickz_internal_network):
        return False
    return _implicit_internal_network(settings)


def _internal_network_inferred_from(settings: APIDeploymentSettings) -> str | None:
    if bool(settings.sickz_internal_network):
        return None
    if (settings.sickz_network_label or "").strip().lower() == "nabla":
        return "SICKZ_NETWORK_LABEL=nabla"
    if (APP_DOMAIN or "").strip().lower() == "albandrieu.albandrieu.com":
        return "APP_DOMAIN=albandrieu.albandrieu.com"
    return None


def _internal_network_effective(settings: APIDeploymentSettings) -> bool:
    if _known_paas_runtime_detected():
        return False
    if bool(settings.sickz_internal_network):
        return True
    return _implicit_internal_network(settings)


def _skip_detail(settings: APIDeploymentSettings) -> str:
    if bool(settings.sickz_internal_network):
        return (
            "Sickz probes are disabled (SICKZ_INTERNAL_NETWORK). This instance is "
            "treated as running on your home LAN where pfSense may be reachable."
        )
    if (settings.sickz_network_label or "").strip().lower() == "nabla":
        return (
            "Sickz probes are disabled: SICKZ_NETWORK_LABEL is 'nabla', so this "
            "instance is treated as on your home LAN."
        )
    return "Sickz probes are disabled."


def _runtime_block(settings: APIDeploymentSettings) -> dict[str, Any]:
    return {
        "cloud_paas_detected": _known_paas_runtime_detected(),
        "sickz_internal_network_config": bool(settings.sickz_internal_network),
        "sickz_internal_network_implicit": _internal_network_implicit(settings),
        "internal_network_inferred_from": _internal_network_inferred_from(settings),
        "sickz_internal_network_effective": _internal_network_effective(settings),
    }
