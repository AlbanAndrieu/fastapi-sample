"""Static contract checks for the TrueNAS platform UI diagnostics."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSET = ROOT / "nabla" / "api" / "assets" / "api-truenas.js"


def test_truenas_platform_displays_public_wan_metadata() -> None:
    javascript = ASSET.read_text(encoding="utf-8")

    assert "diagnostics?.wan" in javascript
    assert "public API path via pfSense/HAProxy" in javascript
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


def test_truenas_platform_distinguishes_direct_lan_from_public_wan_path() -> None:
    javascript = ASSET.read_text(encoding="utf-8")

    assert 'diagnostics?.path_mode === "direct_lan"' in javascript
    assert "TrueNAS HTTPS listener + TrueNAS API (WebSocket /api/current) · direct LAN" in javascript
    assert "public API path via pfSense/HAProxy" in javascript
    assert 'if (pathMode === "direct_lan") return stages;' in javascript


def test_truenas_platform_distinguishes_listener_from_authenticated_api() -> None:
    javascript = ASSET.read_text(encoding="utf-8")

    assert "TrueNAS API access denied after connection" in javascript
    assert "TrueNAS API authorization:" in javascript
    assert "source IP blocked by TrueNAS allowlist" in javascript


def test_truenas_platform_recovers_flow_from_bounded_probe_fallback() -> None:
    javascript = ASSET.read_text(encoding="utf-8")

    assert "fetchHomelabProbeMatrix" in javascript
    assert "needsBoundedProbeFallback" in javascript
    assert "_bounded_probe_fallback" in javascript
    assert "Aggregate homelab diagnostics exceeded their deadline" in javascript


def test_truenas_platform_displays_probe_fanout_matrix() -> None:
    javascript = ASSET.read_text(encoding="utf-8")

    assert "renderProbeFanout" in javascript
    assert "probe_summary" in javascript
    assert "internal_services" in javascript
    assert "public_probe_results" in javascript
    assert "⏸ LAN probes disabled" in javascript
    assert "● LAN probes enabled" in javascript
    assert "TrueNAS HTTPS" in javascript
    assert "TrueNAS API healthy" in javascript
    assert "declared service catalog" in javascript
    assert "TrueNAS app inventory" in javascript
    assert "local/direct LAN" in javascript
    assert "external/public WAN" in javascript
    assert "fan-out budget" in javascript
