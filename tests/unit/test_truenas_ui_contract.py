"""Static contract checks for the TrueNAS platform UI diagnostics."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSET = ROOT / "nabla" / "api" / "assets" / "api-truenas.js"
FLOW_ASSET = ROOT / "nabla" / "api" / "assets" / "api-platform-flow-ui.js"
PROVIDER_ASSET = ROOT / "nabla" / "api" / "assets" / "api-service-probe-details.js"


def test_truenas_platform_displays_public_wan_metadata() -> None:
    javascript = ASSET.read_text(encoding="utf-8")

    assert "diagnostics?.wan" in javascript
    assert "public API path via pfSense/HAProxy" in javascript
    assert "static IPv4" in javascript


def test_truenas_platform_puts_ingress_filters_in_traffic_pipeline() -> None:
    javascript = ASSET.read_text(encoding="utf-8")
    flow = FLOW_ASSET.read_text(encoding="utf-8")

    assert "security_filters" in javascript
    assert "ingressPolicyStage" in javascript
    assert 'id: "pfsense_wan_ingress"' in javascript
    assert 'label: "WAN :7000 via pfSense/HAProxy"' in javascript
    assert "trafficStages" in javascript
    assert 'block?.state === "clear"' in javascript
    assert '"pfSense security posture unconfirmed"' in javascript
    assert 'state = "warn"' in javascript
    assert 'stage?.id === "dns"' in javascript
    assert '"pfSense WAN ingress"' in flow
    assert '"pfSense DNS / Unbound"' in flow
    assert '"Public DNS"' in flow
    assert "DNS provider attribution is not inferred" in flow
    assert '"pfsense"' in flow
    assert "truenas-stage-service-link" in flow


def test_truenas_platform_displays_proven_snort_pf_block() -> None:
    javascript = ASSET.read_text(encoding="utf-8")
    flow = FLOW_ASSET.read_text(encoding="utf-8")

    assert "ingress_block" in javascript
    assert "truenas-ingress-block" in javascript
    assert "Ingress blocked by ${engine} → ${firewall}" in javascript
    assert "FastAPI Cloud egress" not in javascript  # role comes from sanitized API evidence
    assert 'ingressBlock?.state === "blocked"' in javascript
    assert "blocked by Snort/PF" in javascript
    assert 'if (state === "blocked") return;' in flow


def test_unavailable_snort_telemetry_moves_to_pfsense_service_diagnostics() -> None:
    provider = PROVIDER_ASSET.read_text(encoding="utf-8")
    flow = FLOW_ASSET.read_text(encoding="utf-8")

    assert "snort2c evidence unavailable" in provider
    assert "Snort/PF attribution telemetry" in provider
    assert "does not mean Snort or pfBlockerNG is stopped" in provider
    assert "hideUnprovenIngressBanner" in flow
    assert 'if (state === "blocked") return;' in flow


def test_truenas_platform_surfaces_transport_failure_stage() -> None:
    javascript = ASSET.read_text(encoding="utf-8")

    assert 'api?.stage === "connection_reset"' in javascript
    assert "API connection reset" in javascript
    assert 'api?.stage === "tls_handshake_timeout"' in javascript
    assert "TLS handshake timeout" in javascript
    assert 'api?.stage === "api_call_timeout"' in javascript
    assert "API call timeout" in javascript
    assert 'api?.method ? ` · ${api.method}` : ""' in javascript


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


def test_truenas_platform_renders_probe_fanout_from_public_aggregate_snapshot() -> None:
    javascript = ASSET.read_text(encoding="utf-8")

    assert "fetchHomelabProbeMatrix" not in javascript
    assert "const aggregate = await fetchHomelabHealth()" in javascript
    assert "render(aggregate)" in javascript
    assert "lastRenderedSnapshot" in javascript
    assert "_stale_ui_snapshot" in javascript
    assert "Last rendered TrueNAS/probe snapshot retained" in javascript


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
    assert "direct LAN" in javascript
    assert "WAN pfSense/HAProxy" in javascript
    assert "fan-out budget" in javascript


def test_truenas_raw_probe_auth_is_not_a_render_dependency() -> None:
    javascript = ASSET.read_text(encoding="utf-8")

    assert "fetchHomelabProbeMatrix" not in javascript
    assert "const aggregate = await fetchHomelabHealth()" in javascript
    assert "truenas-platform-state--warn" in javascript
    assert "health snapshot unavailable" in javascript
