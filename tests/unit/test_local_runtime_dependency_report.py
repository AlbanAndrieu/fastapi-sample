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
            "components": {
                "postgres": {"reachable": True, "application_ok": True, "application_evidence": {"kind": "sql_select_1", "authenticated": True, "ok": True}},
                "redis": {"reachable": True, "application_ok": True, "application_evidence": {"kind": "redis_ping", "authenticated": True, "ok": True}},
            },
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
        "internal_probe_comparison": {
            "state": "observed", "comparable": 2, "matched": 2,
            "mismatched": 0, "missing_gatus": 0,
        },
        "internal_probe_delegation": {"candidate": True, "blockers": []},
        "platform_metrics": {
            "synthetic_probes": {
                "state": "observed", "gatus_up": 1.0, "service_count": 2,
            },
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

    assert report["schema_version"] == 2
    assert report["snapshot_state"] == "fresh"
    assert report["evidence_complete"] is False
    assert report["evidence_gaps"] == ["sentry", "pyroscope"]

    dependencies = report["dependencies"]
    assert dependencies["truenas"]["evidence_complete"] is True
    assert dependencies["truenas"]["authenticated"] is True
    assert dependencies["truenas"]["application_result"]["app_count"] == 2
    assert dependencies["pfsense"]["authenticated"] is True
    assert dependencies["pfsense"]["application_ok"] is True
    assert dependencies["pfsense"]["operational_state"] == "ok"
    assert dependencies["cloudflare"]["authenticated"] is True
    assert dependencies["prometheus"]["evidence_complete"] is True
    assert dependencies["postgres"]["evidence_complete"] is True
    assert dependencies["redis"]["evidence_complete"] is True
    assert dependencies["gatus"]["evidence_complete"] is True

    assert dependencies["sentry"]["reachable"] is True
    assert dependencies["sentry"]["authenticated"] is None
    assert dependencies["sentry"]["application_result"]["kind"] == "dsn_socket_only"
    assert dependencies["sentry"]["operational_state"] == "evidence_incomplete"
    assert dependencies["sentry"]["evidence_complete"] is False

    assert dependencies["pyroscope"]["reachable"] is True
    assert dependencies["pyroscope"]["application_ok"] is True
    assert dependencies["pyroscope"]["application_result"]["kind"] == "readiness_only"
    assert dependencies["pyroscope"]["evidence_complete"] is False


def test_pfsense_http_response_proves_transport_not_application_success() -> None:
    module = load_module()
    snapshot = sample_snapshot()
    snapshot["healthz"]["checks"]["pfsense"] = {
        "reachable": False,
        "http_status": 502,
        "path": "/api/v2/system/version",
        "credential_mode": "dedicated_posture",
        "error": "pfSense API returned HTTP 502",
        "error_kind": "http_502",
        "failure_stage": "http_response",
        "stale": False,
    }

    row = module.build_report(snapshot)["dependencies"]["pfsense"]

    assert row["configured"] is True
    assert row["reachable"] is True
    assert row["authenticated"] is None
    assert row["application_ok"] is False
    assert row["operational_state"] == "application_error"
    assert row["evidence_complete"] is False


def test_cloudflare_empty_inventory_is_warning_not_outage() -> None:
    module = load_module()
    snapshot = sample_snapshot()
    snapshot["healthz"]["checks"]["cloudflare"] = {
        "reachable": None,
        "api_reachable": True,
        "http_status": 200,
        "status_confirmed": False,
        "state": "unknown",
        "warning": "Cloudflare global status could not be confirmed",
        "error": "Cloudflare Tunnel API returned no tunnel inventory",
        "error_kind": "empty_inventory",
        "stale": False,
    }

    row = module.build_report(snapshot)["dependencies"]["cloudflare"]

    assert row["reachable"] is True
    assert row["authenticated"] is True
    assert row["application_ok"] is False
    assert row["operational_state"] == "warning"
    assert row["evidence_complete"] is False


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
    assert row["operational_state"] == "unreachable"
    assert row["evidence_complete"] is False
    assert row["error_stage"] == "connect_timeout"


def test_prometheus_not_configured_names_required_runtime_setting() -> None:
    module = load_module()
    snapshot = sample_snapshot()
    snapshot["platform_metrics"] = {
        "configured": False,
        "state": "not_configured",
        "summary": {
            "signals_available": 0,
            "signals_total": 6,
            "telemetry_up": 0,
            "telemetry_total": 4,
        },
    }

    row = module.build_report(snapshot)["dependencies"]["prometheus"]

    assert row["configured"] is False
    assert row["reachable"] is None
    assert row["application_ok"] is None
    assert row["error_stage"] == "configuration"
    assert row["error_kind"] == "not_configured"
    assert row["application_result"]["required_setting"] == "HOMELAB_PROMETHEUS_URL"
    assert row["operational_state"] == "configuration_required"


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
    assert row["application_ok"] is False
    assert row["error_stage"] == "query"
    assert row["evidence_complete"] is False


def test_pyroscope_404_proves_http_transport_but_not_readiness() -> None:
    module = load_module()
    snapshot = sample_snapshot()
    snapshot["healthz"]["checks"]["pyroscope"] = {
        "reachable": True,
        "http_status": 404,
        "path": "/health",
        "url": "http://pyroscope.example/health",
    }

    row = module.build_report(snapshot)["dependencies"]["pyroscope"]

    assert row["reachable"] is True
    assert row["application_ok"] is False
    assert row["application_result"]["readiness_ok"] is False
    assert row["operational_state"] == "application_error"
    assert row["evidence_complete"] is False


def test_diagnostic_script_does_not_probe_providers_directly() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    # Human-readable operator guidance may name provider endpoints.
    # Assert that executable network code only calls the cached health-board.
    network_code = source.split("def _fetch_json(", maxsplit=1)[1].split(
        "def _fmt(", maxsplit=1
    )[0]
    assert "/api/health-board" in network_code
    assert "api.cloudflare.com" not in network_code
    assert "/api/v2/system/version" not in network_code
    assert "172.17.0.24:4040" not in network_code
    assert "sentry_sdk" not in network_code
    assert "prometheus/api" not in network_code


def test_pfsense_401_uses_explicit_auth_rejection() -> None:
    module = load_module()
    snapshot = sample_snapshot()
    snapshot["healthz"]["checks"]["pfsense"] = {
        "reachable": True,
        "transport_reachable": True,
        "api_authenticated": False,
        "application_ok": False,
        "application_result": "authentication_rejected",
        "http_status": 401,
        "path": "/api/v2/system/version",
        "credential_mode": "dedicated_posture",
        "state": "warn",
        "failure_stage": "authentication",
        "stale": False,
    }

    row = module.build_report(snapshot)["dependencies"]["pfsense"]

    assert row["reachable"] is True
    assert row["authenticated"] is False
    assert row["application_ok"] is False
    assert row["operational_state"] == "application_error"
    assert row["evidence_complete"] is False
    assert row["application_result"]["application_result"] == "authentication_rejected"


def test_gatus_missing_metrics_is_incomplete_not_internal_service_failure() -> None:
    module = load_module()
    snapshot = sample_snapshot()
    snapshot["platform_metrics"]["synthetic_probes"] = {
        "state": "telemetry_unavailable", "gatus_up": None, "service_count": 0,
    }
    row = module.build_report(snapshot)["dependencies"]["gatus"]
    assert row["evidence_complete"] is False
    assert row["application_ok"] is None
    assert row["application_result"]["external_probes_preserved"] is True


def test_postgres_redis_missing_cache_evidence_is_not_success() -> None:
    module = load_module()
    snapshot = sample_snapshot()
    snapshot["homelab"]["components"] = {}
    report = module.build_report(snapshot)
    for name in ("postgres", "redis"):
        assert report["dependencies"][name]["evidence_complete"] is False
        assert report["dependencies"][name]["reachable"] is None


def test_post_reboot_pending_snapshot_never_passes_global_acceptance() -> None:
    module = load_module()
    snapshot = sample_snapshot()
    snapshot["state"] = "pending"
    report = module.build_report(snapshot)
    assert report["snapshot_fresh"] is False
    assert report["evidence_complete"] is False


def test_stale_snapshot_does_not_pass_even_when_dependencies_are_complete() -> None:
    module = load_module()
    snapshot = sample_snapshot()
    snapshot["stale"] = True
    report = module.build_report(snapshot)
    assert report["snapshot_fresh"] is False
    assert report["evidence_complete"] is False


def test_ready_snapshot_retains_dependency_specific_gaps() -> None:
    module = load_module()
    report = module.build_report(sample_snapshot())
    assert report["snapshot_fresh"] is True
    assert report["evidence_gaps"] == ["sentry", "pyroscope"]


def test_boolean_gatus_service_count_is_not_valid_coverage() -> None:
    module = load_module()
    snapshot = sample_snapshot()
    snapshot["platform_metrics"]["synthetic_probes"]["service_count"] = True
    row = module.build_report(snapshot)["dependencies"]["gatus"]
    assert row["reachable"] is True
    assert row["evidence_complete"] is False
    assert row["operational_state"] == "evidence_incomplete"


def test_unknown_or_missing_snapshot_state_is_never_fresh() -> None:
    module = load_module()
    for state in ("unknown", "refreshing", None):
        snapshot = sample_snapshot()
        if state is None:
            snapshot.pop("state")
        else:
            snapshot["state"] = state
        report = module.build_report(snapshot)
        assert report["snapshot_fresh"] is False
        assert report["evidence_complete"] is False


def test_health_board_timeout_has_clean_operator_error(monkeypatch) -> None:
    module = load_module()

    def timeout(*_args, **_kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(module, "urlopen", timeout)
    try:
        module._fetch_json("http://172.17.0.24:8091/api/health-board", None)
    except RuntimeError as exc:
        assert str(exc) == "health-board request timed out after 8 seconds"
    else:
        raise AssertionError("TimeoutError should be normalized as RuntimeError")


def test_pyroscope_root_200_is_not_a_readiness_failure() -> None:
    module = load_module()
    snapshot = sample_snapshot()
    snapshot["healthz"]["checks"]["pyroscope"] = {
        "reachable": True,
        "http_status": 200,
        "path": "/",
        "url": "http://172.17.0.24:4040/",
    }
    row = module.build_report(snapshot)["dependencies"]["pyroscope"]
    assert row["reachable"] is True
    assert row["application_ok"] is None
    assert row["application_result"]["readiness_ok"] is None
    assert row["operational_state"] == "evidence_incomplete"
    assert row["evidence_complete"] is False


def test_tcp_only_postgres_and_redis_do_not_pass_application_acceptance() -> None:
    module = load_module()
    snapshot = sample_snapshot()
    snapshot["homelab"]["components"] = {
        "postgres": {"reachable": True},
        "redis": {"reachable": True},
    }
    report = module.build_report(snapshot)
    for name in ("postgres", "redis"):
        row = report["dependencies"][name]
        assert row["reachable"] is True
        assert row["application_ok"] is None
        assert row["evidence_complete"] is False
        assert row["operational_state"] == "evidence_incomplete"


def test_truenas_missing_app_inventory_is_unknown_not_application_failure() -> None:
    module = load_module()
    snapshot = sample_snapshot()
    snapshot["homelab"]["truenas"]["api"].pop("apps")
    row = module.build_report(snapshot)["dependencies"]["truenas"]
    assert row["reachable"] is True
    assert row["application_ok"] is None
    assert row["operational_state"] == "evidence_incomplete"
    assert row["evidence_complete"] is False


def test_report_only_preserves_gaps_but_strict_mode_fails(monkeypatch) -> None:
    module = load_module()
    snapshot = sample_snapshot()
    monkeypatch.setattr(
        module, "fetch_converged_snapshot", lambda *_args: snapshot
    )
    monkeypatch.setattr(
        module.sys, "argv", ["diagnose-local-runtime-dependencies.py", "--report-only"]
    )
    assert module.main() == 0
    report = module.build_report(snapshot)
    assert report["evidence_complete"] is False
    assert report["evidence_gaps"] == ["sentry", "pyroscope"]
    monkeypatch.setattr(module.sys, "argv", ["diagnose-local-runtime-dependencies.py"])
    assert module.main() == 1


def test_db_component_requires_authenticated_command_proof() -> None:
    module = load_module()
    snapshot = sample_snapshot()
    for name in ("postgres", "redis"):
        snapshot["homelab"]["components"][name].pop("application_evidence")
    report = module.build_report(snapshot)
    for name in ("postgres", "redis"):
        row = report["dependencies"][name]
        assert row["reachable"] is True
        assert row["application_ok"] is None
        assert row["evidence_complete"] is False


def test_sentry_ingestion_proof_requires_fresh_persisted_event() -> None:
    module = load_module()
    snapshot = sample_snapshot()
    snapshot["healthz"]["checks"]["sentry"]["ingestion_evidence"] = {
        "persisted": True, "fresh": True,
    }
    row = module.build_report(snapshot)["dependencies"]["sentry"]
    assert row["application_ok"] is True
    assert row["evidence_complete"] is True
    snapshot["healthz"]["checks"]["sentry"]["ingestion_evidence"]["fresh"] = False
    assert module.build_report(snapshot)["dependencies"]["sentry"]["evidence_complete"] is False


def test_status_icons_and_ansi_modes_are_explicit() -> None:
    module = load_module()
    assert module._status_label("ok", color=False) == "✅ ok"
    assert module._status_label("unreachable", color=False) == "❌ unreachable"
    assert module._status_label("evidence_incomplete", color=False) == "❔ evidence_incomplete"
    assert (chr(27) + "[") in module._status_label("ok", color=True)
    assert (chr(27) + "[") not in module._status_label("ok", color=False)


def test_text_table_uses_icons_without_ansi_by_default(capsys) -> None:
    module = load_module()
    module.print_table(module.build_report(sample_snapshot()))
    output = capsys.readouterr().out
    assert "✅ ok" in output
    assert "❔ evidence_incomplete" in output
    assert (chr(27) + "[") not in output


def test_basic_availability_does_not_require_deep_acceptance() -> None:
    module = load_module()
    report = module.build_report(sample_snapshot())
    basic = module.basic_availability(report)
    assert basic["sentry"] == "reachable"
    assert basic["pyroscope"] == "reachable"
    assert basic["postgres"] == "reachable"
    assert basic["redis"] == "reachable"
    assert basic["gatus"] == "reachable"
    assert report["evidence_complete"] is False


def test_basic_availability_distinguishes_missing_from_unreachable() -> None:
    module = load_module()
    snapshot = sample_snapshot()
    snapshot["homelab"]["components"].pop("postgres")
    snapshot["healthz"]["checks"]["pyroscope"] = {"reachable": False}
    basic = module.basic_availability(module.build_report(snapshot))
    assert basic["postgres"] == "unknown"
    assert basic["pyroscope"] == "unreachable"


def test_pfsense_denied_and_timeout_do_not_imply_network_down() -> None:
    module = load_module()
    snapshot = sample_snapshot()
    check = snapshot["healthz"]["checks"]["pfsense"]
    check.update({"http_status": 403, "api_authenticated": False, "application_ok": False})
    denied = module.build_report(snapshot)["dependencies"]["pfsense"]
    assert denied["reachable"] is True
    assert denied["authenticated"] is False
    assert denied["evidence_complete"] is False
    check.clear()
    check.update({"configured": True, "error_kind": "connect_timeout"})
    timeout = module.build_report(snapshot)["dependencies"]["pfsense"]
    assert timeout["authenticated"] is None
    assert timeout["evidence_complete"] is False


def test_recovered_pyroscope_readiness_remains_separate_from_profile_ingestion() -> None:
    module = load_module()
    snapshot = sample_snapshot()
    check = snapshot["healthz"]["checks"]["pyroscope"]
    check.update({"http_status": 200, "path": "/ready"})
    ready = module.build_report(snapshot)["dependencies"]["pyroscope"]
    assert ready["reachable"] is True
    assert ready["application_ok"] is True
    assert ready["evidence_complete"] is False


def test_stale_component_and_real_command_failure_stay_distinct() -> None:
    module = load_module()
    snapshot = sample_snapshot()
    postgres = snapshot["homelab"]["components"]["postgres"]
    postgres["stale"] = True
    assert module.build_report(snapshot)["dependencies"]["postgres"]["evidence_complete"] is False
    postgres["stale"] = False
    postgres["application_evidence"]["ok"] = False
    failed = module.build_report(snapshot)["dependencies"]["postgres"]
    assert failed["application_ok"] is False
    assert failed["operational_state"] == "application_error"
