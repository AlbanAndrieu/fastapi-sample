"""Keep the external ingress policy separate from workload failures."""

from __future__ import annotations

import pytest

from nabla.api import sickz_policy
from nabla.api.homelab_models import HomelabService
from nabla.api.homelab_runtime import ObservedApp, TrueNASRuntimeSnapshot


@pytest.mark.asyncio
async def test_sickz_security_policy_does_not_turn_red_only_because_app_crashed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "https://bichon.albandrieu.com/"
    service = HomelabService(
        name="Bichon",
        tunnel_url=url,
        tunnel_secure=False,
        external=False,
    )
    runtime = TrueNASRuntimeSnapshot(
        observed_at="2026-10-25T01:00:00Z",
        configured=True,
        reachable=True,
        apps=[ObservedApp(app_id="bichon", name="bichon", state="CRASHED")],
    )

    async def services():
        return [service]

    async def cloudflare():
        return [], [], True, None, None

    async def truenas():
        return runtime

    async def edge(_url, **_kwargs):
        return {"cloudflare_http_evidence": False}

    monkeypatch.setattr(sickz_policy, "fetch_homelab_services", services)
    monkeypatch.setattr(sickz_policy, "_observe_cloudflare", cloudflare)
    monkeypatch.setattr(sickz_policy, "fetch_truenas_runtime", truenas)
    monkeypatch.setattr(sickz_policy, "_probe_http_edge_evidence", edge)

    result = await sickz_policy.enrich_sickz_policy(
        {"checks": {
            "bichon": {
                "tunnel_url": url,
                "reachable": False,
                "http_status": 502,
            }
        }}
    )
    check = result["checks"]["bichon"]
    assert check["security_policy_status"] == "ok"
    assert "not reachable" in check["security_policy_detail"]
    # Existing /sickz behavior is retained for workload diagnostics.
    assert check["policy_status"] == "fail"
    assert check["runtime_failed"] is True
    assert check["runtime_state"] == "CRASHED"
