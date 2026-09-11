"""Static contracts for per-service DNS and Cloudflare operator badges."""

from pathlib import Path


ASSETS = Path("nabla/api/assets")


def test_dns_badge_exposes_runtime_resolver_evidence() -> None:
    javascript = (ASSETS / "api-dns-status.js").read_text(encoding="utf-8")

    assert 'label.textContent = "DNS"' in javascript
    assert "dns_latency_ms" in javascript
    assert "dns_resolvers" in javascript
    assert "dns_resolved" in javascript
    assert "dns_resolver_source" in javascript
    assert "strip.prepend(badgeFor(check))" in javascript


def test_health_controller_decorates_dns_from_existing_snapshot() -> None:
    javascript = (ASSETS / "api-health-controller.js").read_text(encoding="utf-8")

    assert 'from "./api-dns-status.js"' in javascript
    assert "decorateDnsStatuses(snapshot)" in javascript


def test_cloudflare_badge_keeps_tunnel_state_and_policy_in_hover_only() -> None:
    javascript = (ASSETS / "api-cloudflare-probe.js").read_text(encoding="utf-8")

    assert "selfhst/icons@main/svg/cloudflare.svg" in javascript
    assert '"Cloudflare Tunnel unverified"' in javascript
    assert "cloudflare_access_policy_names" in javascript
    assert "cloudflare_access_policy_decisions" in javascript
    assert "badge.title = hover" in javascript
    assert 'text.textContent = "Tunnel"' in javascript
    assert 'row.querySelectorAll(".cloudflare-tunnel-badge")' in javascript


def test_health_controller_reconciles_cloudflare_probe_after_sickz_render() -> None:
    javascript = (ASSETS / "api-health-controller.js").read_text(encoding="utf-8")

    assert 'from "./api-cloudflare-probe.js"' in javascript
    assert "decorateCloudflareProbeStatuses(snapshot.sickz)" in javascript
