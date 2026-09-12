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
    assert 'label: "pfSense WAN ingress"' in javascript
    assert "trafficStages" in javascript
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


def test_truenas_platform_renders_bounded_probes_before_aggregate_enrichment() -> None:
    javascript = ASSET.read_text(encoding="utf-8")
    flow = FLOW_ASSET.read_text(encoding="utf-8")

    probe_fetch = javascript.index("probes = await fetchHomelabProbeMatrix()")
    probe_render = javascript.index("_probe_first: true", probe_fetch)
    aggregate_fetch = javascript.index("const aggregate = await fetchHomelabHealth()")

    assert probe_fetch < probe_render < aggregate_fetch
    assert "needsBoundedProbeFallback" in javascript
    assert "_bounded_probe_fallback" in javascript
    assert "_aggregate_enrichment_error" in javascript
    assert "Aggregate homelab diagnostics exceeded their deadline" in javascript
    assert "removeImplementationNote" in flow
    assert "TrueNAS flow rendered from bounded /api/homelab/probes first" in flow


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
