"""Static contract checks for the TrueNAS platform UI diagnostics."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSET = ROOT / "nabla" / "api" / "assets" / "api-truenas.js"


def test_truenas_platform_displays_public_wan_metadata() -> None:
    javascript = ASSET.read_text(encoding="utf-8")

    assert "diagnostics?.wan" in javascript
    assert "pfSense WAN / homelab public endpoint ${wan.ipv4}" in javascript
    assert "static IPv4" in javascript


def test_truenas_platform_puts_ingress_filters_in_traffic_pipeline() -> None:
    javascript = ASSET.read_text(encoding="utf-8")

    assert "security_filters" in javascript
    assert "ingressPolicyStage" in javascript
    assert 'id: "pfsense_wan_ingress"' in javascript
    assert 'label: "pfSense WAN ingress"' in javascript
    assert "trafficStages" in javascript
    assert 'stage?.id === "dns"' in javascript


def test_truenas_platform_displays_proven_snort_pf_block() -> None:
    javascript = ASSET.read_text(encoding="utf-8")

    assert "ingress_block" in javascript
    assert "truenas-ingress-block" in javascript
    assert "Ingress blocked by ${engine} → ${firewall}" in javascript
    assert "FastAPI Cloud egress" not in javascript  # role comes from sanitized API evidence
    assert 'ingressBlock?.state === "blocked"' in javascript
    assert "blocked by Snort/PF" in javascript


def test_truenas_platform_displays_shared_wan_diagnostic_blind_spot() -> None:
    javascript = ASSET.read_text(encoding="utf-8")

    assert 'block?.state === "telemetry_unavailable"' in javascript
    assert "controlPath?.blind_spot === true" in javascript
    assert "Snort attribution unavailable · self-diagnostic blind spot" in javascript
