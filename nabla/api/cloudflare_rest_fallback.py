"""Bounded read-only Cloudflare REST fallback for observer SDK failures.

The official SDK remains the primary observer. This module mirrors only the
small set of GET endpoints used by the health board so a provider-side SDK
request regression (for example ``BadRequestError``) does not turn valid
read-only credentials into false downtime.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from nabla.api.cloudflare_tunnels import (
    CloudflareAccessApplicationObservation,
    CloudflareAccessControlPlaneObservation,
    CloudflareAccessPolicyObservation,
    CloudflareTunnelIngress,
    CloudflareTunnelObservation,
    CloudflareTunnelSettings,
)

_API_ROOT = "https://api.cloudflare.com/client/v4"
_TIMEOUT_SECONDS = 5.0
_DEFAULT_PROJECT_POLICY = "fastapi-sample-monitor"
_DEFAULT_PROJECT_SERVICE_TOKEN = "fastapi-sample-monitor"


def _project_policy_name() -> str:
    return (
        os.getenv("CLOUDFLARE_PROJECT_ACCESS_POLICY_NAME", "").strip()
        or _DEFAULT_PROJECT_POLICY
    )


def _project_service_token_name() -> str:
    return (
        os.getenv("CLOUDFLARE_PROJECT_SERVICE_TOKEN_NAME", "").strip()
        or _DEFAULT_PROJECT_SERVICE_TOKEN
    )


def _safe_error(exc: BaseException) -> str:
    if isinstance(exc, HTTPError):
        return f"HTTP {exc.code}"
    if isinstance(exc, URLError):
        return "transport_error"
    return exc.__class__.__name__[:80]


def _get(settings: CloudflareTunnelSettings, path: str) -> dict[str, Any]:
    url = f"{_API_ROOT}{path}"
    request = Request(  # noqa: S310 - fixed HTTPS provider origin
        url,
        headers={
            "Authorization": f"Bearer {settings.api_token}",
            "Accept": "application/json",
            "User-Agent": "fastapi-sample-cloudflare-observer/1",
        },
    )
    try:
        with urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # nosec B310  # noqa: S310
            payload = json.load(response)
    except (HTTPError, URLError) as exc:
        raise RuntimeError(_safe_error(exc)) from exc
    if not isinstance(payload, dict):
        raise RuntimeError("unexpected_response")
    if payload.get("success") is not True:
        raise RuntimeError("provider_rejected_request")
    return payload


def _metadata(payload: dict[str, Any], observed: int) -> dict[str, int]:
    info = payload.get("result_info")
    if not isinstance(info, dict):
        return {"result_count": observed, "total_count": observed}
    try:
        count = int(info.get("count", observed))
    except (TypeError, ValueError):
        count = observed
    try:
        total = int(info.get("total_count", count))
    except (TypeError, ValueError):
        total = count
    return {"result_count": count, "total_count": total}


def _items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("result")
    if not isinstance(result, list):
        return []
    return [item for item in result if isinstance(item, dict)]


def observe_tunnels_rest(
    settings: CloudflareTunnelSettings,
) -> tuple[list[CloudflareTunnelObservation], dict[str, int]]:
    """Read active tunnels and Cloudflare-managed ingress through REST."""
    account = quote(settings.account_id, safe="")
    payload = _get(settings, f"/accounts/{account}/cfd_tunnel")
    observations: list[CloudflareTunnelObservation] = []
    inactive = 0
    for item in _items(payload):
        if str(item.get("status") or "").strip().lower() == "inactive":
            inactive += 1
            continue
        tunnel_id = str(item.get("id") or "").strip()
        if not tunnel_id:
            continue
        name = str(item.get("name") or tunnel_id)
        status = str(item.get("status") or "") or None
        config_source = str(item.get("config_src") or "") or None
        ingress: list[CloudflareTunnelIngress] = []
        if config_source == "cloudflare":
            try:
                config_payload = _get(
                    settings,
                    f"/accounts/{account}/cfd_tunnel/{quote(tunnel_id, safe='')}/configurations",
                )
                result = config_payload.get("result")
                config = result.get("config") if isinstance(result, dict) else None
                rules = config.get("ingress") if isinstance(config, dict) else None
                if isinstance(rules, list):
                    for rule in rules:
                        if not isinstance(rule, dict):
                            continue
                        hostname = str(rule.get("hostname") or "").strip().lower().rstrip(".")
                        service = str(rule.get("service") or "").strip()
                        if not hostname:
                            continue
                        ingress.append(
                            CloudflareTunnelIngress(
                                tunnel_id=tunnel_id,
                                tunnel_name=name,
                                hostname=hostname,
                                service=service,
                                status=status,
                            ),
                        )
            except RuntimeError:
                # Tunnel liveness/inventory remains valid even if optional ingress
                # configuration is temporarily unavailable.
                ingress = []
        observations.append(
            CloudflareTunnelObservation(
                tunnel_id=tunnel_id,
                name=name,
                status=status,
                config_source=config_source,
                ingress=tuple(ingress),
            ),
        )
    metadata = _metadata(payload, len(observations))
    metadata["result_count"] = len(observations)
    metadata["inactive_filtered"] = inactive
    return observations, metadata


def _policy_observation(item: dict[str, Any]) -> CloudflareAccessPolicyObservation | None:
    policy_id = str(item.get("id") or "").strip()
    if not policy_id:
        return None
    include = item.get("include")
    includes_everyone = False
    if isinstance(include, list):
        includes_everyone = any(
            isinstance(rule, dict) and "everyone" in rule for rule in include
        )
    return CloudflareAccessPolicyObservation(
        policy_id=policy_id,
        name=str(item.get("name")) if item.get("name") is not None else None,
        decision=(
            str(item.get("decision")).lower()
            if item.get("decision") is not None
            else None
        ),
        includes_everyone=includes_everyone,
    )


def observe_access_applications_rest(
    settings: CloudflareTunnelSettings,
) -> tuple[list[CloudflareAccessApplicationObservation], dict[str, int]]:
    """Read Access applications without expanding account-wide policy calls."""
    account = quote(settings.account_id, safe="")
    payload = _get(settings, f"/accounts/{account}/access/apps")
    observations: list[CloudflareAccessApplicationObservation] = []
    for item in _items(payload):
        app_id = str(item.get("id") or "").strip()
        domain = str(item.get("domain") or "").strip()
        if not app_id or not domain:
            continue
        candidate = domain if "://" in domain else f"https://{domain}"
        from urllib.parse import urlsplit

        parsed = urlsplit(candidate)
        hostname = (parsed.hostname or "").lower().rstrip(".")
        if not hostname:
            continue
        policies: list[CloudflareAccessPolicyObservation] = []
        raw_policies = item.get("policies")
        if isinstance(raw_policies, list):
            for raw_policy in raw_policies:
                if not isinstance(raw_policy, dict):
                    continue
                policy = _policy_observation(raw_policy)
                if policy is not None:
                    policies.append(policy)
        observations.append(
            CloudflareAccessApplicationObservation(
                app_id=app_id,
                name=str(item.get("name") or app_id),
                domain=domain,
                hostname=hostname,
                path=parsed.path or "/",
                policies=tuple(policies),
            ),
        )
    return observations, _metadata(payload, len(observations))


def observe_project_access_control_plane_rest(
    settings: CloudflareTunnelSettings,
) -> CloudflareAccessControlPlaneObservation:
    """Observe only FastAPI Sample's reusable policy and Service Token."""
    account = quote(settings.account_id, safe="")
    policy_name = _project_policy_name()
    token_name = _project_service_token_name()

    reusable_policy_count: int | None = None
    reusable_policy_app_count: int | None = None
    reusable_policy_elapsed_ms: int | None = None
    reusable_policy_error: str | None = None
    started = time.perf_counter()
    try:
        payload = _get(settings, f"/accounts/{account}/access/policies")
        policies = [
            item
            for item in _items(payload)
            if str(item.get("name") or "").strip() == policy_name
        ]
        reusable_policy_count = len(policies)
        reusable_policy_app_count = sum(
            max(0, int(item.get("app_count") or 0)) for item in policies
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        reusable_policy_error = _safe_error(exc)
    reusable_policy_elapsed_ms = round((time.perf_counter() - started) * 1000)

    service_token_count: int | None = None
    service_token_enabled_count: int | None = None
    service_token_elapsed_ms: int | None = None
    service_token_error: str | None = None
    configured_service_token_present: bool | None = None
    started = time.perf_counter()
    try:
        payload = _get(settings, f"/accounts/{account}/access/service_tokens")
        tokens = [
            item
            for item in _items(payload)
            if str(item.get("name") or "").strip() == token_name
        ]
        service_token_count = len(tokens)
        service_token_enabled_count = sum(
            item.get("enabled", True) is not False for item in tokens
        )
        configured_client_id = os.getenv("CF_ACCESS_CLIENT_ID", "").strip()
        if configured_client_id:
            ids = {str(item.get("client_id") or "").strip() for item in tokens}
            configured_service_token_present = configured_client_id in ids
            if not any(ids):
                configured_service_token_present = bool(tokens)
        else:
            configured_service_token_present = bool(tokens)
    except RuntimeError as exc:
        service_token_error = _safe_error(exc)
    service_token_elapsed_ms = round((time.perf_counter() - started) * 1000)

    return CloudflareAccessControlPlaneObservation(
        reusable_policy_count=reusable_policy_count,
        reusable_policy_total_count=reusable_policy_count,
        reusable_policy_app_count=reusable_policy_app_count,
        reusable_policy_elapsed_ms=reusable_policy_elapsed_ms,
        reusable_policy_error=reusable_policy_error,
        service_token_count=service_token_count,
        service_token_total_count=service_token_count,
        service_token_enabled_count=service_token_enabled_count,
        service_token_elapsed_ms=service_token_elapsed_ms,
        service_token_error=service_token_error,
        configured_service_token_present=configured_service_token_present,
    )
