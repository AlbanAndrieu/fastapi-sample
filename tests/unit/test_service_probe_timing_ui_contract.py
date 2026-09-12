"""Static contracts for per-service HTTP and timing diagnostics."""

from pathlib import Path


ASSETS = Path("nabla/api/assets")


def test_http_200_is_transport_green_and_hover_has_timing() -> None:
    javascript = (ASSETS / "api-http-probe-status.js").read_text(encoding="utf-8")

    assert 'if (status >= 200 && status < 400) return "ok";' in javascript
    assert "elapsed_ms ?? check?.latency_ms" in javascript
    assert "last-run=" in javascript
    assert "cadence=" in javascript
    assert "next-due=" in javascript
    assert "PENDING / probing…" in javascript
    assert "badge.classList.add(`service-probe--${toneFor(check)}`)" in javascript


def test_question_help_reuses_http_probe_timing() -> None:
    javascript = (ASSETS / "api-service-probe-help.js").read_text(encoding="utf-8")
    entrypoint = (ASSETS / "api-health.js").read_text(encoding="utf-8")

    assert 'row.querySelector(\'[data-probe-kind="http"]\')' in javascript
    assert "HTTP probe:" in javascript
    assert "aria-label" in javascript
    assert 'from "./api-service-probe-help.js"' in entrypoint
    assert "installServiceProbeHelp();" in entrypoint


def test_service_drawer_exposes_probe_timing_and_freshness_layers() -> None:
    javascript = (ASSETS / "api-service-probe-details.js").read_text(encoding="utf-8")

    for text in (
        "Probe timing & freshness",
        "Health probe",
        "Homelab probe",
        "Exposure / edge probe",
        "Probe state",
        "Probe latency",
        "DNS latency",
        "Last probe",
        "Probe age",
        "Cadence",
        "Next due",
        "Refresh error",
    ):
        assert text in javascript
    assert "probe_observed_at" in javascript
    assert "probe_interval_seconds" in javascript
    assert "next_probe_in_seconds" in javascript
    assert "snapshot?.refreshing" in javascript


def test_dependency_lists_use_canonical_lifecycle_priority() -> None:
    javascript = (ASSETS / "api-service-dependency-priority.js").read_text(
        encoding="utf-8",
    )
    entrypoint = (ASSETS / "api-health.js").read_text(encoding="utf-8")

    assert '"bootstrap-runtime", 0' in javascript
    assert '"applications", 6' in javascript
    assert "lifecycle.priority" in javascript
    assert "leftOptional" in javascript
    assert "criticality" in javascript
    assert 'from "./api-service-dependency-priority.js"' in entrypoint
    assert "installServiceDependencyPriority" in entrypoint


def test_local_managed_tunnel_wording_does_not_claim_missing_ingress() -> None:
    javascript = (ASSETS / "api-cloudflare-local-managed.js").read_text(encoding="utf-8")

    assert "local_managed_tunnels" in javascript
    assert "per-host ingress cannot be verified through the remote Cloudflare API" in javascript
    assert "Cloudflare edge headers are present" in javascript
    assert ".cloudflare-tunnel-badge, .service-probe" in javascript


def test_health_entrypoints_wire_probe_enhancements() -> None:
    controller = (ASSETS / "api-health-controller.js").read_text(encoding="utf-8")
    entrypoint = (ASSETS / "api-health.js").read_text(encoding="utf-8")

    assert 'from "./api-http-probe-status.js"' in controller
    assert "decorateHttpProbeStatuses(snapshot)" in controller
    assert 'from "./api-cloudflare-local-managed.js"' in controller
    assert "decorateLocalManagedTunnelWording" in controller
    assert 'from "./api-service-probe-details.js"' in entrypoint
    assert "installServiceProbeDetails();" in entrypoint
    assert "installHttpProbeStatuses();" in entrypoint
