from pathlib import Path


ASSETS = Path("nabla/api/assets")


def test_probe_planes_reuse_homelab_public_and_internal_evidence() -> None:
    source = (ASSETS / "api-service-probe-planes.js").read_text(encoding="utf-8")

    assert "snapshot?.homelab?.public_probe_results" in source
    assert "snapshot?.homelab?.services" in source
    assert "snapshot?.homelab?.internal_services" in source
    assert 'mode === "homelab" || mode === "local"' in source
    assert 'data-probe-plane="lan"' in source
    # Public remains the first canonical strip and receives its marker via dataset.
    assert 'data-probe-plane="public"' not in source


def test_fastapi_cloud_does_not_render_a_fake_lan_plane() -> None:
    source = (ASSETS / "api-service-probe-planes.js").read_text(encoding="utf-8")

    assert "localPlanesEnabled(snapshot)" in source
    assert 'mode === "homelab" || mode === "local"' in source
    assert "FastAPI Cloud" not in source


def test_cloudflare_badges_have_distinct_routing_and_authorization_meanings() -> None:
    source = (ASSETS / "api-service-probe-planes.js").read_text(encoding="utf-8")

    assert '"Tunnel"' in source
    assert "Published application route" in source
    assert "Tunnel provides routing/connectivity" in source
    assert '"Access"' in source
    assert "authorization layer" in source
    assert '"Token"' in source
    assert "machine identity used by an Access Service Auth policy" in source
    assert 'CLOUDFLARE_DASHBOARD = "https://one.dash.cloudflare.com/"' in source
    assert "linkedBadge(tunnel, CLOUDFLARE_DASHBOARD)" in source
    assert "linkedBadge(access, CLOUDFLARE_DASHBOARD)" in source
    assert "linkedBadge(token, CLOUDFLARE_DASHBOARD)" in source
    assert "/networks/connectors/cloudflare-tunnels/" not in source
    assert "/access-controls/service-credentials/service-tokens/" not in source


def test_external_and_token_badges_keep_stable_visible_width() -> None:
    source = (ASSETS / "api-service-probe-planes.js").read_text(encoding="utf-8")

    assert 'badgeLabel(badge, "external")' in source
    assert 'ensureProbe(strip, "service-token", "🔑", "Token")' in source
    assert "cloudflare_service_token_http_status" in source


def test_probe_timing_uses_fixed_side_column_and_homelab_public_evidence() -> None:
    source = (ASSETS / "api-probe-live.js").read_text(encoding="utf-8")
    stylesheet = (ASSETS / "api-service-probe-planes.css").read_text(
        encoding="utf-8",
    )

    assert "health-row-telemetry" in source
    assert "snapshot?.homelab?.public_probe_results" in source
    assert "health-meta-badge--probe-latency" in source
    assert "health-meta-badge--probing" in source
    assert ".health-row-telemetry" in stylesheet
    assert "position: absolute" in stylesheet
    assert "font-variant-numeric: tabular-nums" in stylesheet


def test_pfsense_security_posture_distinguishes_path_from_observation() -> None:
    source = (ASSETS / "api-pfsense-security-posture.js").read_text(
        encoding="utf-8",
    )

    assert 'pathMode === "direct_lan"' in source
    assert "out-of-band from current LAN probe" in source
    assert "pfSense WAN ingress security posture" in source
    assert "security_filters" in source
    assert "read-only pfSense control path" in source
