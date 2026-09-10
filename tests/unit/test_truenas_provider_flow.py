"""Regression coverage for TrueNAS route and out-of-band provider stages."""

from nabla.api.homelab_health_evidence import _enrich_truenas_flow


def _payload(path_mode: str = "direct_lan") -> dict:
    return {
        "truenas": {
            "public": {"url": "https://truenas.albandrieu.com:7000"},
            "diagnostics": {
                "path_mode": path_mode,
                "stages": [
                    {
                        "id": "dns",
                        "label": "DNS",
                        "state": "ok",
                        "resolved": ["172.17.0.24"],
                    },
                    {"id": "socket", "label": "TCP", "state": "ok"},
                ],
            },
        }
    }


def _pfsense() -> dict:
    return {
        "policy_state": "ok",
        "resolver": {"running": True, "enabled": True},
        "service_summary": {"running": 2, "stopped": 1, "unknown": 0, "total": 3},
        "services": [
            {"identity": "unbound dns resolver", "runtime_state": "running"},
            {"identity": "snort wan", "runtime_state": "running"},
            {"identity": "crowdsec", "runtime_state": "stopped"},
        ],
        "security_filters": [
            {"label": "pfSense/PF firewall", "state": "in_path"},
            {"label": "Snort", "state": "running"},
            {"label": "CrowdSec", "state": "stopped"},
        ],
    }


def test_direct_lan_flow_starts_with_actual_target_and_keeps_pfsense_out_of_band() -> None:
    enriched = _enrich_truenas_flow(
        _payload(),
        pfsense_dns=_pfsense(),
        cloudflare={
            "configured": True,
            "status_confirmed": True,
            "tunnels_observed": 4,
        },
    )

    stages = enriched["truenas"]["diagnostics"]["stages"]
    assert stages[0]["id"] == "selected_endpoint"
    assert "https://truenas.albandrieu.com:7000" in stages[0]["detail"]
    assert "172.17.0.24" in stages[0]["detail"]
    assert "TLS/SNI" in stages[0]["detail"]

    ids = [stage["id"] for stage in stages]
    assert ids.index("pfsense_lan_posture") == ids.index("dns") + 1
    pfsense = stages[ids.index("pfsense_lan_posture")]
    assert pfsense["state"] == "ok"
    assert "Unbound=running" in pfsense["detail"]
    assert "stopped: crowdsec" in pfsense["detail"]
    assert "not on the direct TrueNAS LAN data path" in pfsense["detail"]

    assert stages[-1]["id"] == "cloudflare_tunnel_observation"
    assert stages[-1]["state"] == "ok"
    assert "observational only" in stages[-1]["detail"]


def test_cloudflare_uncertainty_is_warning_not_failed_truenas_path() -> None:
    enriched = _enrich_truenas_flow(
        _payload(),
        pfsense_dns=_pfsense(),
        cloudflare={
            "configured": True,
            "status_confirmed": False,
            "warning": "⚠️ Cloudflare global status could not be confirmed: timeout",
        },
    )

    stage = enriched["truenas"]["diagnostics"]["stages"][-1]
    assert stage["id"] == "cloudflare_tunnel_observation"
    assert stage["state"] == "warn"
    assert "could not be confirmed" in stage["detail"]


def test_public_wan_flow_does_not_invent_lan_pfsense_stage() -> None:
    enriched = _enrich_truenas_flow(
        _payload(path_mode="public_wan"),
        pfsense_dns=_pfsense(),
        cloudflare={"configured": False, "status_confirmed": False},
    )

    ids = [stage["id"] for stage in enriched["truenas"]["diagnostics"]["stages"]]
    assert "pfsense_lan_posture" not in ids
    assert ids[0] == "selected_endpoint"
    assert ids[-1] == "cloudflare_tunnel_observation"
