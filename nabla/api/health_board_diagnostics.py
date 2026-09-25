# ruff: noqa: PLC0415 -- optional probes stay lazy.
"""Optional health-board diagnostic builders isolated from cache orchestration."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
import logging
from typing import Any

from fastapi import Request

from nabla.api.health_contracts import apply_diagnostic_status

logger = logging.getLogger(__name__)


def _deadline_check(probe: str) -> dict[str, Any]:
    return {
        "reachable": False,
        "timed_out": True,
        "error": "optional diagnostic enrichment deadline exceeded",
        "error_kind": "deadline",
        "probe": probe,
    }


def cloudflare_unconfirmed_check(
    *,
    error: str,
    error_kind: str,
    timed_out: bool = False,
) -> dict[str, Any]:
    return {
        "reachable": None,
        "api_reachable": None,
        "state": "unknown",
        "status_confirmed": False,
        "warning": f"⚠️ Cloudflare global status could not be confirmed: {error}",
        "timed_out": timed_out,
        "error": error,
        "error_kind": error_kind,
        "probe": "cloudflare",
    }


def _failed_optional_check(
    probe: str,
    exc: BaseException | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "reachable": False,
        "error": "optional diagnostic enrichment failed",
        "error_kind": "probe_error",
        "probe": probe,
    }
    if exc is not None:
        result["exception_type"] = type(exc).__name__
    return result


async def build_extended_healthz(
    request: Request,
    *,
    reconciliation_context: Awaitable[dict[str, Any]] | None = None,
    deadline_seconds: float,
) -> dict[str, Any]:
    """Build deep diagnostics with a caller-owned enrichment deadline."""
    from nabla.api.db.database import engine
    from nabla.api.demo.socket.redis import redis
    from nabla.api.health_checks import build_healthz_payload
    from nabla.api.homelab_provider_reuse import (
        platform_checks_from_reconciliation_context,
    )
    from nabla.api.observability_health import (
        enrich_optional_observability_checks,
    )
    from nabla.api.platform_health import enrich_optional_platform_checks

    payload = await build_healthz_payload(
        request,
        redis_client=redis,
        engine=engine,
    )

    async def platform_checks() -> dict[str, Any]:
        try:
            async with asyncio.timeout(deadline_seconds):
                if reconciliation_context is not None:
                    context = await asyncio.shield(reconciliation_context)
                    return await platform_checks_from_reconciliation_context(
                        context,
                    )
                enriched = await enrich_optional_platform_checks(payload)
        except TimeoutError:
            return {
                "cloudflare": cloudflare_unconfirmed_check(
                    error="optional diagnostic enrichment deadline exceeded",
                    error_kind="deadline",
                    timed_out=True,
                ),
                "pfsense": _deadline_check("pfsense"),
            }
        except Exception as exc:
            logger.warning(
                "optional platform health enrichment failed exception_type=%s",
                type(exc).__name__,
            )
            return {
                "cloudflare": cloudflare_unconfirmed_check(
                    error="optional diagnostic enrichment failed",
                    error_kind="probe_error",
                ),
                "pfsense": _failed_optional_check("pfsense", exc),
            }
        checks = enriched.get("checks") or {}
        return {
            "cloudflare": checks.get(
                "cloudflare",
                _failed_optional_check("cloudflare"),
            ),
            "pfsense": checks.get(
                "pfsense",
                _failed_optional_check("pfsense"),
            ),
        }

    async def observability_checks() -> dict[str, Any]:
        try:
            async with asyncio.timeout(deadline_seconds):
                enriched = await enrich_optional_observability_checks(payload)
        except TimeoutError:
            return {"logfire": _deadline_check("logfire")}
        except Exception as exc:
            logger.warning(
                "optional observability health enrichment failed exception_type=%s",
                type(exc).__name__,
            )
            return {"logfire": _failed_optional_check("logfire", exc)}
        checks = enriched.get("checks") or {}
        return {
            "logfire": checks.get(
                "logfire",
                _failed_optional_check("logfire"),
            ),
        }

    platform, observability = await asyncio.gather(
        platform_checks(),
        observability_checks(),
    )
    checks = dict(payload.get("checks") or {})
    checks.update(platform)
    checks.update(observability)
    return apply_diagnostic_status({**payload, "checks": checks})


async def build_sickz_snapshot(
    request: Request,
    *,
    deadline_seconds: float,
) -> dict[str, Any]:
    """Build sickz plus bounded policy enrichment."""
    from nabla.api.runtime_environment import runtime_mode
    from nabla.api.sickz_checks import build_sickz_payload
    from nabla.api.sickz_policy import enrich_sickz_policy
    from nabla.api.sickz_port_annotations import (
        enrich_pfsense_port_annotations,
    )

    payload = await build_sickz_payload(request)
    try:
        async with asyncio.timeout(deadline_seconds):
            payload = await enrich_sickz_policy(payload)
    except TimeoutError:
        payload = {
            **payload,
            "policy_enrichment": {
                "status": "timeout",
                "timed_out": True,
                "error_kind": "deadline",
            },
        }
    except Exception as exc:
        logger.warning(
            "sickz policy enrichment failed exception_type=%s",
            type(exc).__name__,
        )
        payload = {
            **payload,
            "policy_enrichment": {
                "status": "failed",
                "error_kind": "probe_error",
                "exception_type": type(exc).__name__,
            },
        }
    return enrich_pfsense_port_annotations(
        payload,
        runtime_scope=runtime_mode(request.url.hostname),
    )


async def build_runtime_snapshot(
    request: Request | None = None,
) -> dict[str, Any]:
    """Return the shared runtime/egress view used by the public API page."""
    from nabla.api.demo.socket.redis import redis
    from nabla.api.runtime_topology import build_runtime_topology_snapshot

    hostname = request.url.hostname if request is not None else None
    return await build_runtime_topology_snapshot(redis, hostname=hostname)
