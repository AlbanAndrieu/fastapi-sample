"""Static contracts for the live homelab probe fan-out dashboard."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = ROOT / "nabla" / "api" / "assets" / "api-probe-fanout-dashboard.js"
SHARED = ROOT / "nabla" / "api" / "assets" / "api-homelab-health.js"
BOOTSTRAP = ROOT / "nabla" / "api" / "assets" / "api-health.js"
STYLES = ROOT / "nabla" / "api" / "assets" / "api.css"


def test_probe_dashboard_reuses_existing_probe_fetch_events() -> None:
    shared = SHARED.read_text(encoding="utf-8")
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")

    assert '"homelab-probes:update"' in shared
    assert '"homelab-probes:loading"' in shared
    assert '"homelab-probes:error"' in shared
    assert "installProbeFanoutDashboard" in bootstrap
    assert 'fetchHomelabProbeMatrix({ reason: "manual" })' in DASHBOARD.read_text(
        encoding="utf-8",
    )


def test_probe_dashboard_separates_latest_and_retained_evidence() -> None:
    javascript = DASHBOARD.read_text(encoding="utf-8")

    assert 'row?.probe_source === "origin"' in javascript
    assert 'row?.probe_source === "deadline"' in javascript
    assert 'row?.probe_source === "memory"' in javascript
    assert "Latest rotating wave" in javascript
    assert "Retained previous evidence" in javascript
    assert "probe_observed_at" not in javascript  # age/cadence are the operator-facing fields
    assert "probe_age_seconds" in javascript
    assert "probe_interval_seconds" in javascript
    assert "next_probe_in_seconds" in javascript


def test_probe_dashboard_exposes_coverage_health_and_runtime_warmup() -> None:
    javascript = DASHBOARD.read_text(encoding="utf-8")

    assert "evidence coverage" in javascript
    assert "healthy coverage" in javascript
    assert "Evidence warm-up" in javascript
    assert "probe_runtime" in javascript
    assert "scheduler uptime" in javascript
    assert "longest priority-aware cadence" in javascript
    assert "Excluded from coverage denominator" in javascript
    assert "eligible probe slots" in javascript
    assert "probe-coverage-segment--${kind}" in javascript
    assert 'progressSegment(counts.ok, eligible, "ok"' in javascript
    assert 'progressSegment(counts.fail, eligible, "fail"' in javascript
    assert "const { counts, eligible, unknown } = model;" in javascript
    assert "`${unknown} not yet observed`" in javascript


def test_probe_dashboard_keeps_targets_and_states_in_separate_cells() -> None:
    javascript = DASHBOARD.read_text(encoding="utf-8")

    assert "probe-dashboard-target" in javascript
    assert "probe-state-badge" in javascript
    assert 'target="_blank" rel="noopener noreferrer"' in javascript
    assert "rowDetail(row)" in javascript
    assert "service probe fan-out budget exceeded" not in javascript


def test_probe_dashboard_clarifies_runtime_timeout_when_raw_api_is_healthy() -> None:
    javascript = DASHBOARD.read_text(encoding="utf-8")

    assert "TrueNAS runtime: Call timeout" in javascript
    assert "the raw TrueNAS API probe is healthy" in javascript
    assert "does not mark the platform down" in javascript


def test_probe_dashboard_styles_are_loaded() -> None:
    styles = STYLES.read_text(encoding="utf-8")

    assert '@import url("./api-probe-fanout-dashboard.css");' in styles


def test_probe_dashboard_exposes_operator_triage_without_new_fanout() -> None:
    javascript = DASHBOARD.read_text(encoding="utf-8")

    assert "Problems only" in javascript
    assert "All scopes" in javascript
    assert "Copy diagnostics" in javascript
    assert "matchesOperatorFilter" in javascript
    assert "captureStateChanges" in javascript
    assert "errorCategory" in javascript
    assert 'state !== "ok" && (row?.http_status || kind.includes("http"))' in javascript
    assert "freshness ${(age / interval).toFixed(1)}x cadence" in javascript
    assert "phase 4/4 · rolling evidence ready" in javascript
    assert "sanitizedDiagnostics" in javascript
    assert 'fetchHomelabProbeMatrix({ reason: "manual" })' in javascript
    assert "fetch(" not in javascript
