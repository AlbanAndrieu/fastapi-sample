"""Multi-provider orchestration tests for homelab health."""

import asyncio

from nabla.api import homelab_health_evidence as module
from nabla.api.homelab_models import HomelabService
from nabla.api.homelab_runtime import TrueNASRuntimeSnapshot
from nabla.api.homelab_topology import HomelabTopology


def test_runtime_error_and_cloudflare_uncertainty_are_preserved(monkeypatch) -> None:
    service = HomelabService(
        name="TrueNAS-dependent service",
        tunnelUrl="https://example.albandrieu.com",
        external=True,
    )
    runtime = TrueNASRuntimeSnapshot(
        observed_at="2026-09-10T18:00:00Z",
        configured=True,
        reachable=False,
        error="connect timeout",
    )

    async def services():
        return [service]

    async def declared():
        class Catalog:
            services = []

        return Catalog()

    async def runtime_probe():
        return runtime

    async def cloudflare_probe():
        class Cloudflare:
            tunnels = []
            access_applications = []
            stale = True
            configured = True

            def summary(self):
                return {
                    "status_confirmed": False,
                    "warning": "⚠️ Cloudflare global status could not be confirmed",
                }

        return Cloudflare()

    async def topology():
        return HomelabTopology()

    async def dns(**_kwargs):
        return {}

    monkeypatch.setattr(module, "fetch_homelab_services", services)
    monkeypatch.setattr(module, "fetch_declared_service_catalog", declared)
    monkeypatch.setattr(module, "fetch_truenas_runtime", runtime_probe)
    monkeypatch.setattr(module, "observe_cloudflare_exposure", cloudflare_probe)
    monkeypatch.setattr(module, "fetch_homelab_topology", topology)
    monkeypatch.setattr(module, "observe_pfsense_dns_posture", dns)

    payload = asyncio.run(module.reconcile_homelab_health_payload({"services": []}))

    assert payload["truenas_runtime_reachable"] is False
    assert payload["truenas_runtime_error"] == "connect timeout"
    assert payload["cloudflare"]["status_confirmed"] is False
    assert payload["reconciliation"]["provider_reads_reused"] is True
    assert payload["reconciliation"]["evidence_priority"] == [
        "truenas_runtime",
        "http_https_tcp",
        "required_dependencies",
        "pfsense",
        "cloudflare",
        "prometheus",
    ]


def test_context_reads_independent_providers_once(monkeypatch) -> None:
    calls = {"declared": 0, "cloudflare": 0, "topology": 0, "pfsense": 0}

    async def declared():
        calls["declared"] += 1
        return object()

    async def cloudflare():
        calls["cloudflare"] += 1
        return object()

    async def topology():
        calls["topology"] += 1
        return object()

    async def pfsense(**_kwargs):
        calls["pfsense"] += 1
        return object()

    monkeypatch.setattr(module, "fetch_declared_service_catalog", declared)
    monkeypatch.setattr(module, "observe_cloudflare_exposure", cloudflare)
    monkeypatch.setattr(module, "fetch_homelab_topology", topology)
    monkeypatch.setattr(module, "observe_pfsense_dns_posture", pfsense)

    context = asyncio.run(module.prepare_homelab_reconciliation_context([]))

    assert set(context) == {
        "services",
        "declared",
        "cloudflare",
        "topology",
        "pfsense_dns",
        "performance_phases_ms",
    }
    assert set(context["performance_phases_ms"]) == {
        "declared_catalog",
        "cloudflare_exposure",
        "topology",
        "pfsense_posture",
    }
    assert calls == {"declared": 1, "cloudflare": 1, "topology": 1, "pfsense": 1}
