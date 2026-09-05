# ruff: noqa: C901, PLC0415 -- route-local imports keep optional probes lazy.

"""Health and homelab route registration.

Keep dependency probes and diagnostic endpoints isolated from the general application
route module. The public paths and response contracts intentionally remain unchanged.
"""

from __future__ import annotations

from typing import Annotated, Any

import pyroscope
from fastapi import FastAPI, Query, Request, Response, status
from fastapi.responses import JSONResponse

from nabla.api.homelab_declared import DeclaredServiceCatalog
from nabla.api.homelab_models import HomelabCatalog
from nabla.api.homelab_runtime import TrueNASRuntimeSnapshot
from nabla.api.homelab_topology import HomelabTopology
from nabla.utils.logger import logger


_NO_STORE_HEADERS = {"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"}


def register_health_routes(app: FastAPI) -> None:
    """Register health, homelab and observability diagnostic routes."""

    @app.get(
        "/api/homelab-services",
        response_model=HomelabCatalog,
        response_model_exclude_none=True,
        tags=["Homelab"],
        summary="FastAPI-owned homelab exposure catalog",
    )
    async def get_homelab_services():
        """Expose the FastAPI-owned presentation and exposure policy catalog."""
        from nabla.api.homelab_catalog import fetch_homelab_catalog

        return await fetch_homelab_catalog()

    @app.get(
        "/api/homelab/declared-services",
        response_model=DeclaredServiceCatalog,
        response_model_exclude_none=True,
        tags=["Homelab"],
        summary="Code-owned declared homelab services",
    )
    async def get_declared_homelab_services() -> DeclaredServiceCatalog:
        """Expose the service inventory generated from nabla-compose x-nabla metadata."""
        from nabla.api.homelab_declared import fetch_declared_service_catalog

        return await fetch_declared_service_catalog()

    @app.get(
        "/api/homelab-topology",
        response_model=HomelabTopology,
        response_model_exclude_none=True,
        tags=["Homelab"],
        summary="Declared homelab service topology",
    )
    async def get_homelab_topology() -> HomelabTopology:
        """Expose the validated design-time topology sourced from nabla-compose."""
        from nabla.api.homelab_topology import fetch_homelab_topology

        return await fetch_homelab_topology()

    @app.get(
        "/api/homelab/runtime",
        response_model=TrueNASRuntimeSnapshot,
        response_model_exclude_none=True,
        tags=["Homelab", "TrueNAS"],
        summary="Observed TrueNAS application runtime",
    )
    async def get_homelab_runtime() -> TrueNASRuntimeSnapshot:
        """Expose a sanitized app.query snapshot from the official TrueNAS client."""
        from nabla.api.homelab_runtime import fetch_truenas_runtime

        return await fetch_truenas_runtime()

    @app.get(
        "/api/homelab/status",
        tags=["Homelab", "TrueNAS"],
        summary="Declared versus observed homelab status",
    )
    async def get_homelab_status() -> dict[str, Any]:
        """Reconcile declarations/runtime and expose provider credential presence only."""
        from nabla.api.homelab_runtime import build_homelab_status_payload
        from nabla.api.provider_credentials import infrastructure_provider_credentials

        payload = await build_homelab_status_payload()
        payload["providerCredentials"] = infrastructure_provider_credentials()
        return payload

    @app.get(
        "/api/homelab/health",
        tags=["Homelab", "Health"],
        summary="Homelab and platform health",
    )
    async def get_homelab_health() -> dict[str, Any]:
        """Return detailed homelab services plus shared core/platform components."""
        from nabla.api.health_board import build_homelab_snapshot

        return await build_homelab_snapshot()

    @app.get(
        "/api/runtime/topology",
        tags=["Health", "Runtime"],
        summary="Observed application runtimes and public egress",
    )
    async def get_runtime_topology(request: Request, response: Response) -> dict[str, Any]:
        """Expose sanitized cross-replica heartbeat and egress evidence."""
        from nabla.api.demo.socket.redis import redis
        from nabla.api.runtime_topology import build_runtime_topology_snapshot

        response.headers.update(_NO_STORE_HEADERS)
        return await build_runtime_topology_snapshot(
            redis,
            hostname=request.url.hostname,
        )

    @app.get(
        "/livez",
        tags=["Health"],
        summary="Process liveness without dependency I/O",
        operation_id="get_liveness",
    )
    async def get_liveness(response: Response) -> dict[str, Any]:
        from nabla.api.health_contracts import build_liveness_payload

        response.headers.update(_NO_STORE_HEADERS)
        return build_liveness_payload(version=app.version)

    @app.get(
        "/readyz",
        tags=["Health"],
        summary="Readiness of traffic-critical dependencies",
        operation_id="get_readiness",
    )
    async def get_readiness() -> JSONResponse:
        from nabla.api.db.database import engine
        from nabla.api.demo.socket.redis import redis
        from nabla.api.health_contracts import build_readiness_payload

        payload, ready = await build_readiness_payload(
            redis_client=redis,
            engine=engine,
            version=app.version,
        )
        return JSONResponse(
            payload,
            status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
            headers=_NO_STORE_HEADERS,
        )

    @app.get(
        "/healthz",
        tags=["Health"],
        summary="Deep healthcheck",
    )
    async def get_healthz(request: Request, response: Response) -> dict[str, Any]:
        """Return runtime health plus deep dependency and service probes."""
        from nabla.api.health_board import build_extended_healthz

        response.headers.update(_NO_STORE_HEADERS)
        with pyroscope.tag_wrapper({"function": "fast"}):
            return await build_extended_healthz(request)

    @app.get(
        "/sickz",
        tags=["Health"],
        summary="Exposure security policy",
    )
    async def get_sickz(request: Request, response: Response) -> dict[str, Any]:
        """Compare declared external/Cloudflare policy with observed reachability."""
        from nabla.api.health_board import build_sickz_snapshot

        response.headers.update(_NO_STORE_HEADERS)
        with pyroscope.tag_wrapper({"function": "fast"}):
            return await build_sickz_snapshot(request)

    @app.get(
        "/api/health-board",
        tags=["Health", "Runtime"],
        summary="Cached API health-board snapshot",
    )
    async def get_health_board(request: Request, response: Response) -> dict[str, Any]:
        """Return the shared health-board snapshot consumed by the API landing page."""
        from nabla.api.health_board import get_health_board_snapshot

        response.headers.update(_NO_STORE_HEADERS)
        return await get_health_board_snapshot(request)

    @app.get(
        "/api/homelab/declared-services/compact",
        tags=["Homelab"],
        summary="Compact declared homelab service catalog",
    )
    async def get_declared_homelab_services_compact() -> dict[str, Any]:
        from nabla.api.homelab_declared import fetch_declared_service_catalog

        catalog = await fetch_declared_service_catalog()
        return {
            "schema_version": catalog.schema_version,
            "source": catalog.source,
            "service_count": len(catalog.services),
            "services": [
                {
                    "key": service.key,
                    "display_name": service.display_name,
                    "tier": service.tier,
                    "external": service.external,
                    "tunnel_secure": service.tunnel_secure,
                }
                for service in catalog.services
            ],
        }

    @app.get(
        "/api/homelab/observed-runtime",
        tags=["Homelab", "Runtime"],
        summary="Compact observed TrueNAS runtime",
    )
    async def get_observed_homelab_runtime() -> dict[str, Any]:
        from nabla.api.homelab_runtime import fetch_truenas_runtime

        snapshot = await fetch_truenas_runtime()
        return snapshot.model_dump(mode="json", exclude_none=True)

    @app.get(
        "/api/homelab/observed-status",
        tags=["Homelab", "Runtime"],
        summary="Compact reconciled homelab status",
    )
    async def get_observed_homelab_status() -> dict[str, Any]:
        from nabla.api.homelab_runtime import build_homelab_status_payload

        return await build_homelab_status_payload()

    @app.get(
        "/api/homelab/observed-topology",
        tags=["Homelab", "Runtime"],
        summary="Compact observed homelab topology",
    )
    async def get_observed_homelab_topology() -> dict[str, Any]:
        from nabla.api.homelab_topology import fetch_homelab_topology

        topology = await fetch_homelab_topology()
        return topology.model_dump(mode="json", exclude_none=True)

    @app.get(
        "/api/homelab/refresh",
        tags=["Homelab", "Runtime"],
        summary="Explicit homelab health refresh",
    )
    async def refresh_homelab_health(request: Request) -> dict[str, Any]:
        """Force-refresh the cached health board and return the resulting snapshot."""
        from nabla.api.health_board import force_health_board_refresh

        return await force_health_board_refresh(request)

    @app.get(
        "/api/homelab/probe-budget",
        tags=["Homelab", "Health"],
        summary="Current aggregate health probe budget",
    )
    async def get_probe_budget() -> dict[str, Any]:
        from nabla.api.probe_budget import probe_budget_snapshot

        return probe_budget_snapshot()

    @app.get(
        "/api/homelab/provider-credentials",
        tags=["Homelab", "Health"],
        summary="Provider credential presence without secret values",
    )
    async def get_provider_credentials() -> dict[str, Any]:
        from nabla.api.provider_credentials import infrastructure_provider_credentials

        return infrastructure_provider_credentials()

    @app.get(
        "/api/homelab/provider-policies",
        tags=["Homelab", "Health"],
        summary="External provider probe-cache policies",
    )
    async def get_provider_policies() -> dict[str, Any]:
        from nabla.api.provider_probe_policies import provider_probe_policies_snapshot

        return provider_probe_policies_snapshot()

    @app.get(
        "/api/homelab/provider-circuits",
        tags=["Homelab", "Health"],
        summary="Current provider-circuit states",
    )
    async def get_provider_circuits() -> dict[str, Any]:
        from nabla.api.provider_circuit import provider_circuit_snapshot

        return provider_circuit_snapshot()

    @app.get(
        "/api/homelab/public-egress",
        tags=["Homelab", "Runtime"],
        summary="Current public egress observation",
    )
    async def get_public_egress() -> dict[str, Any]:
        from nabla.api.public_egress_observer import observe_public_egress_ip

        return await observe_public_egress_ip()

    @app.get(
        "/api/homelab/declared-network",
        tags=["Homelab", "Runtime"],
        summary="Current declared network context",
    )
    async def get_declared_network() -> dict[str, Any]:
        from nabla.api.sickz_runtime import sickz_network_context

        return sickz_network_context()

    @app.get(
        "/api/homelab/pfsense-source-policy",
        tags=["Homelab", "pfSense", "Security"],
        summary="Sanitized pfSense trusted-source policy diagnostic",
    )
    async def get_pfsense_source_policy(request: Request) -> dict[str, Any]:
        from nabla.api.health_board import build_extended_healthz, build_runtime_snapshot

        healthz = await build_extended_healthz(request)
        runtime = await build_runtime_snapshot(request)
        return {
            "runtime": {
                "provider": runtime.get("provider"),
                "runtime_mode": runtime.get("runtime_mode"),
                "active_egress_ips": runtime.get("active_egress_ips"),
                "recent_egress_ips": runtime.get("recent_egress_ips"),
            },
            "pfsense": (healthz.get("checks") or {}).get("pfsense"),
        }
