"""Offline Gatus-to-FastAPI metric reconciliation contracts."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/reconcile-gatus-coverage.py"
spec = importlib.util.spec_from_file_location("reconcile_gatus_coverage", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

NOW = datetime(2026, 10, 25, 14, 0, tzinfo=UTC)


def config():
    return {"endpoints": [
        {"name": "Gatus", "url": "tcp://operator:secret@localhost:8085", "extra-labels": {"nabla_monitor_id": "gatus", "nabla_service_id": "gatus"}},
        {"name": "Redis", "url": "tcp://localhost:6379", "extra-labels": {"nabla_monitor_id": "redis", "nabla_service_id": "redis"}},
        {"name": "API", "url": "http://localhost:8091/health", "extra-labels": {"nabla_monitor_id": "fastapi-sample", "nabla_service_id": "fastapi-sample"}},
    ]}


def snapshot(services=None, **changes):
    metrics = {"generated_at": NOW.isoformat(), "synthetic_probes": {
        "state": "observed", "gatus_up": 1.0, "services": services or {},
    }}
    metrics.update(changes)
    return {"platform_metrics": metrics}


def test_mixed_outcomes_cannot_be_globally_green():
    result = module.reconcile(config(), snapshot({
        "gatus": {"TCP": {"success": 1}},
        "redis": {"TCP": {"success": 0}},
    }), now=NOW)
    assert result["counts"] == {"up": 1, "down": 1, "no_sample": 1, "unverified": 0}
    assert result["declared_count"] == 3
    assert result["observed_count"] == 2
    assert result["checks"]["down"][0]["service_id"] == "redis"


def test_missing_snapshot_does_not_turn_checks_red():
    result = module.reconcile(config(), None, now=NOW)
    assert result["counts"]["unverified"] == 3
    assert result["counts"]["down"] == 0


def test_stale_or_truncated_snapshot_cannot_prove_up():
    stale = snapshot({}, generated_at=(NOW - timedelta(minutes=5)).isoformat())
    assert module.reconcile(config(), stale, now=NOW)["state"] == "snapshot_stale"
    truncated = snapshot({})
    truncated["platform_metrics"]["synthetic_probes"]["truncated"] = True
    assert module.reconcile(config(), truncated, now=NOW)["state"] == "truncated"


def test_boolean_invalid_and_nan_samples_are_unknown():
    result = module.reconcile(config(), snapshot({
        "gatus": {"TCP": {"success": True}},
        "redis": {"TCP": {"success": float("nan")}},
    }), now=NOW)
    assert result["counts"]["no_sample"] == 3


def test_unexpected_observations_are_not_declared_as_monitors():
    result = module.reconcile(config(), snapshot({
        "outside": {"HTTP": {"success": 1}},
    }), now=NOW)
    assert result["unmatched_observed"] == [{"service_id": "outside", "protocol": "HTTP"}]


def test_duplicate_and_invalid_labels_are_warned_without_leaking_urls():
    conf = config()
    conf["endpoints"].append(conf["endpoints"][0])
    conf["endpoints"].append({"url": "http://unknown:secret@private", "extra-labels": {}})
    result = module.reconcile(conf, None, now=NOW)
    assert "duplicate_monitor:gatus" in result["warnings"]
    assert "missing_canonical_service_id:4" in result["warnings"]
    assert "secret" not in str(result)


def test_unsupported_protocol_is_not_mislabeled_http():
    conf = {"endpoints": [{"url": "icmp://internal", "extra-labels": {
        "nabla_monitor_id": "host", "nabla_service_id": "host",
    }}]}
    result = module.reconcile(conf, None, now=NOW)
    assert result["declared_count"] == 0
    assert result["warnings"] == ["unsupported_protocol:host"]


def test_fail_closed_on_oversized_input_and_unbounded_endpoints(tmp_path):
    path = tmp_path / "large.yml"
    with path.open("wb") as handle:
        handle.truncate(module.MAX_FILE_BYTES + 1)
    try:
        module.load_document(path, as_yaml=True)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected size rejection")
    try:
        module.declared_checks({"endpoints": [{}] * (module.MAX_MONITORS + 1)})
    except ValueError:
        pass
    else:
        raise AssertionError("Expected size rejection")
