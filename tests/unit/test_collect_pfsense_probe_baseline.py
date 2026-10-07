"""Tests for the passive pfSense Prometheus baseline collector."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "collect_pfsense_probe_baseline.py"
)
SPEC = importlib.util.spec_from_file_location(
    "collect_pfsense_probe_baseline", SCRIPT_PATH
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _vector(*items: tuple[dict[str, str], str]) -> list[dict[str, object]]:
    return [
        {"metric": labels, "value": [1_760_000_000, value]}
        for labels, value in items
    ]


def test_validate_window_rejects_promql_injection() -> None:
    assert MODULE.validate_window("30m") == "30m"
    assert MODULE.validate_window("6h") == "6h"
    with pytest.raises(ValueError, match="positive Prometheus duration"):
        MODULE.validate_window('30m]) or vector(1)')


def test_build_queries_use_only_fixed_cardinality_metrics() -> None:
    queries = MODULE.build_queries("30m")
    rendered = "\n".join(queries.values())

    assert len(queries) == 7
    assert "[30m]" in rendered
    assert "Nabla-Probe-Request-ID" not in rendered
    assert "request_id" not in rendered
    assert 'provider="pfsense"' in rendered
    assert "nabla_pfsense_preflight_duration_seconds_bucket" in rendered
    assert "nabla_pfsense_api_requests_total" in rendered


def test_query_prometheus_normalizes_url_and_requires_vector() -> None:
    captured: dict[str, object] = {}

    def fetch_json(base_url: str, promql: str, timeout: float) -> dict[str, object]:
        captured["base_url"] = base_url
        captured["promql"] = promql
        captured["timeout"] = timeout
        return {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": _vector(({"phase": "preflight"}, "2")),
            },
        }

    result = MODULE.query_prometheus(
        "http://prometheus.test/",
        'sum(rate(metric{label="value"}[30m]))',
        timeout=2.0,
        fetch_json=fetch_jsom,
    )

    assert result[0]["metric"] == {"phase": "preflight"}
    assert captured["timeout"] == 2.0
    assert captured["base_url"] == "http://prometheus.test"
    assert captured["promql"] == 'sum(rate(metric{label="value"}[30m]))'


def test_summarize_results_preserves_protection_boundary() -> None:
    report = MODULE.summarize_results(
        {
            "preflight_p95_seconds": _vector(({}, "1.75")),
            "preflight_p99_seconds": _vector(({}, "2.4")),
            "protective_skips": _vector(
                ({"reason": "slow_preflight"}, "3"),
                ({"reason": "authentication_failure"}, "1"),
            ),
            "api_requests": _vector(
                ({"phase": "preflight"}, "30"),
                ({"phase": "deep"}, "60"),
            ),
            "max_api_requests_in_flight": _vector(
                ({"phase": "preflight"}, "1"),
                ({"phase": "deep"}, "2"),
            ),
            "max_provider_origins_in_flight": _vector(({}, "1")),
            "max_provider_rate_budget_utilization_ratio": _vector(({}, "0.5")),
        },
        window="30m",
        generated_at="2026-10-07T19:00:00+00:00",
    )

    assert report["direct_pfsense_requests"] == 0
    assert report["metrics"]["preflight_p95_seconds"] == 1.75
    assert report["metrics"]["preflight_p99_seconds"] == 2.4
    assert report["metrics"]["protective_skips"] == {
        "authentication_failure": 1.0,
        "slow_preflight": 3.0,
    }
    assert report["metrics"]["max_api_requests_in_flight"] == {
        "deep": 2.0,
        "preflight": 1.0,
    }
    assert report["assessment"]["p95_target_met"] is True
    assert report["assessment"]["protection_threshold_seconds"] == 2.5
    assert report["assessment"]["threshold_change_allowed"] is False
    assert "PHP-FPM worker evidence" in report["assessment"][
        "threshold_change_blocked_by"
    ]
    assert report["warnings"] == []


def test_summarize_results_treats_nan_as_missing_evidence() -> None:
    report = MODULE.summarize_results(
        {
            "preflight_p95_seconds": _vector(({}, "NaN")),
            "preflight_p99_seconds": [],
        },
        window="30m",
        generated_at="2026-10-07T19:00:00+00:00",
    )

    assert report["metrics"]["preflight_p95_seconds"] is None
    assert report["metrics"]["preflight_p99_seconds"] is None
    assert report["assessment"]["p95_target_met"] is None
    assert report["warnings"] == [
        "preflight_p95_seconds_unavailable",
        "preflight_p99_seconds_unavailable",
    ]
