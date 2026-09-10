from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "diagnose-local-runtime-dependencies.py"


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("runtime_dependency_report", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_snapshot() -> dict:
    return {
        "state": "fresh",
        "generated_at": "2026-09-10T18:00:00Z",
        "age_seconds": 1.0,
        "homelab": {
            "probe_cache": {"stale": False},
            "truenas": {
                "state": "ok",
                "api": {
                    "reachable": True,
                    "apps": [{"name": "scrutiny"}, {"name": "sentry"}],
                },
                "diagnostics": {"path_mode": "direct_lan"},
            },
        },
        "healthz": {
            "checks": {
                "pfsense": {
                    "reachable": True,
                    "http_status": 200,
                    "path": "/api/v2/system/version",
                    "credential_mode": "posture",
                    "stale": False,
                },
                "cloudflare": {
                    "reachable": True,
                    "api_reachable": True,
                    "http_status": 200,
                    "status_confirmed": True,
                    "tunnel_count": 4,
                    "healthy_tunnels": 4,
                    "unhealthy_tunnels": 0,
                    "stale": False,
                },
                "sentry": {
                    "reachable": True,
                    "probe": "dsn_socket",
                    "target": "local",
                },
                "pyroscope": {
                    "reachable": True,
                    "http_status": 200,
                    "path": "/ready",
                    "url": "http://172.17.0.24:4040/ready",
                },
            },
        },
        "platform_metrics": {
            "configured": True,
            "state": "healthy",
            "summary": {
                "signals_available": 6,
                "signals_total": 6,
                "telemetry_up": 4,
                "telemetry_total": 4,
            },
        },
    }


def test_report_reuses_existing_snapshot_and_exposes_depth_gaps() -> None:
    module = load_module()

    report = module.build_report(sample_snapshot())

    assert report["snapshot_state"] == "fresh"
    assert report["evidence_complete"] is False
    assert report["evidence_gaps"] == ["sentry", "pyroscope"]

    dependencies = report["dependencies"]
    assert dependencies["truenas"]["evidence_complete"] is True
    assert dependencies["truenas"]["authenticated"] is True
    assert dependencies["truenas"]["application_result"]["app_count"] == 2
    assert dependencies["pfsense"]["authenticated"] is True
    assert dependencies["cloudflare"]["authenticated"] is True
    assert dependencies["prometheus"]["evidence_complete"] is True

    assert dependencies["sentry"]["reachable"] is True
    assert dependencies["sentry"]["authenticated"] is None
    assert dependencies["sentry"]["application_result"]["kind"] == "dsn_socket_only"
    assert dependencies["sentry"]["evidence_complete"] is False

    assert dependencies["pyroscope"]["reachable"] is True
    assert dependencies["pyroscope"]["application_result"]["kind"] == "readiness_only"
    assert dependencies["pyroscope"]["evidence_complete"] is False


def test_cloudflare_uncertainty_stays_unknown_not_authenticated() -> None:
    module = load_module()
    snapshot = sample_snapshot()
    snapshot["healthz"]["checks"]["cloudflare"] = {
        "reachable": None,
        "api_reachable": False,
        "status_confirmed": False,
        "state": "unknown",
        "warning": "Cloudflare status could not be confirmed",
        "error_kind": "connect_timeout",
        "stale": True,
    }

    row = module.build_report(snapshot)["dependencies"]["cloudflare"]

    assert row["reachable"] is False
    assert row["authenticated"] is None
    assert row["stale"] is True
    assert row["evidence_complete"] is False
    assert row["error_stage"] == "connect_timeout"


def test_prometheus_query_failure_is_classified_as_query_stage() -> None:
    module = load_module()
    snapshot = sample_snapshot()
    snapshot["platform_metrics"] = {
        "configured": True,
        "state": "telemetry_unavailable",
        "error_kind": "query_failed",
        "summary": {
            "signals_available": 0,
            "signals_total": 6,
            "telemetry_up": 0,
            "telemetry_total": 4,
        },
    }

    row = module.build_report(snapshot)["dependencies"]["prometheus"]

    assert row["configured"] is True
    assert row["reachable"] is False
    assert row["error_stage"] == "query"
    assert row["evidence_complete"] is False


def test_diagnostic_script_does_not_probe_providers_directly() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "/api/health-board" in source
    assert "api.cloudflare.com" not in source
    assert "/api/v2/system/version" not in source
    assert "172.17.0.24:4040" not in source
    assert "sentry_sdk" not in source
    assert "prometheus/api" not in source
