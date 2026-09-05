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


def test_truenas_platform_distinguishes_unavailable_and_stale_snort_telemetry() -> None:
    javascript = ASSET.read_text(encoding="utf-8")

    assert 'block?.state === "telemetry_unavailable"' in javascript
    assert "pfSense security telemetry temporarily unavailable" in javascript
    assert "Control path:" in javascript
    assert 'block?.state === "telemetry_stale"' in javascript
    assert "Snort telemetry stale · last-known-good table retained" in javascript
    assert "No current clear/blocked verdict is emitted from stale data." in javascript


def test_truenas_platform_surfaces_transport_failure_stage() -> None:
    javascript = ASSET.read_text(encoding="utf-8")

    assert 'api?.stage === "connection_reset"' in javascript
    assert "API connection reset" in javascript
    assert 'api?.stage === "tls_handshake_timeout"' in javascript
    assert "TLS handshake timeout" in javascript
    assert 'api?.stage === "api_call_timeout"' in javascript
    assert "API call timeout" in javascript
