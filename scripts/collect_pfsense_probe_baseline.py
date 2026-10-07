"""Collect passive pfSense probe baseline evidence from Prometheus only."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

_WINDOW_RE = re.compile(r"^[1-9]\d*[smhdwy]$")
_DEFAULT_WINDOW = "30m"
_DEFAULT_TIMEOUT_SECONDS = 3.0
_PROTECTION_THRESHOLD_SECONDS = 2.5
_P95_TARGET_SECONDS = 2.0
_USER_AGENT = "fastapi-sample-pfsense-baseline/1.0"

JsonFetcher = Callable[[str, str, float], dict[str, Any]]


def validate_window(window: str) -> str:
    """Validate a bounded Prometheus range selector without PromQL injection."""
    normalized = window.strip()
    if _WINDOW_RE.fullmatch(normalized) is None:
        raise ValueError(
            "window must be a positive Prometheus duration such as 30m, 1h or 6h"
        )
    return normalized


def build_queries(window: str) -> dict[str, str]:
    """Return fixed-cardinality PromQL queries for passive pfSense evidence."""
    validated = validate_window(window)
    return {
        "preflight_p95_seconds": (
            "histogram_quantile(0.95, sum by (le) (rate("
            "nabla_pfsense_preflight_duration_seconds_bucket{outcome=\"success\"}"
            f"[{validated}])))"
        ),
        "preflight_p99_seconds": (
            "histogram_quantile(0.99, sum by (le) (rate("
            "nabla_pfsense_preflight_duration_seconds_bucket{outcome=\"success\"}"
            f"[{validated}])))"
        ),
        "protective_skips": (
            "sum by (reason) (increase("
            f"nabla_pfsense_protective_skips_total[{validated}]))"
        ),
        "api_requests": (
            "sum by (phase) (increase("
            f"nabla_pfsense_api_requests_total[{validated}]))"
        ),
        "max_api_requests_in_flight": (
            "max by (phase) (max_over_time("
            f"nabla_pfsense_api_requests_in_flight[{validated}]))"
        ),
        "max_provider_origins_in_flight": (
            "max(max_over_time("
            "nabla_external_provider_origins_in_flight{provider=\"pfsense\"}"
            f"[{validated}]))"
        ),
        "max_provider_rate_budget_utilization_ratio": (
            "max(max_over_time("
            "nabla_external_provider_rate_budget_utilization_ratio"
            "{provider=\"pfsense\"}"
            f"[{validated}]))"
        ),
    }


def _default_fetch_json(
    base_url: str,
    promql: str,
    timeout: float,
) -> dict[str, Any]:
    response = httpx.get(
        f"{base_url}/api/v1/query",
        params={"query": promql},
        headers={"Accept": "application/json", "User-Agent": _USER_AGENT},
        timeout=timeout,
        follow_redirects=False,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Prometheus returned a non-object JSON payload")
    return payload


def query_prometheus(
    base_url: str,
    promql: str,
    *,
    timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    fetch_json: JsonFetcher = _default_fetch_json,
) -> list[dict[str, Any]]:
    """Execute one Prometheus instant query and return its vector result."""
    if timeout <= 0 or timeout > 10:
        raise ValueError("timeout must be greater than 0 and no more than 10 seconds")
    normalized_url = base_url.strip().rstrip("/")
    if not normalized_url:
        raise ValueError("Prometheus URL is required")

    payload = fetch_json(normalized_url, promql, timeout)
    if payload.get("status") != "success":
        raise RuntimeError("Prometheus query failed")
    data = payload.get("data")
    if not isinstance(data, dict) or data.get("resultType") != "vector":
        raise RuntimeError("Prometheus query did not return a vector")
    result = data.get("result")
    if not isinstance(result, list):
        raise RuntimeError("Prometheus vector result is malformed")
    return [item for item in result if isinstance(item, dict)]


def _sample_number(item: dict[str, Any]) -> float | None:
    value = item.get("value")
    if not isinstance(value, list) or len(value) != 2:
        return None
    try:
        number = float(value[1])
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _scalar(result: list[dict[str, Any]]) -> float | None:
    values = [_sample_number(item) for item in result]
    finite = [value for value in values if value is not None]
    if len(finite) != 1:
        return None
    return finite[0]


def _vector_by_label(
    result: list[dict[str, Any]],
    label: str,
) -> dict[str, float]:
    values: dict[str, float] = {}
    for item in result:
        metric = item.get("metric")
        if not isinstance(metric, dict):
            continue
        label_value = metric.get(label)
        number = _sample_number(item)
        if not isinstance(label_value, str) or number is None:
            continue
        values[label_value] = number
    return dict(sorted(values.items()))


def summarize_results(
    raw_results: dict[str, list[dict[str, Any]]],
    *,
    window: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a bounded, secret-free baseline report from Prometheus vectors."""
    p95 = _scalar(raw_results.get("preflight_p95_seconds", []))
    p99 = _scalar(raw_results.get("preflight_p99_seconds", []))
    warnings: list[str] = []
    if p95 is None:
        warnings.append("preflight_p95_seconds_unavailable")
    if p99 is None:
        warnings.append("preflight_p99_seconds_unavailable")

    return {
        "schema_version": 1,
        "generated_at": generated_at or datetime.now(UTC).isoformat(),
        "window": validate_window(window),
        "source": "prometheus",
        "direct_pfsense_requests": 0,
        "metrics": {
            "preflight_p95_seconds": p95,
            "preflight_p99_seconds": p99,
            "protective_skips": _vector_by_label(
                raw_results.get("protective_skips", []), "reason"
            ),
            "api_requests": _vector_by_label(
                raw_results.get("api_requests", []), "phase"
            ),
            "max_api_requests_in_flight": _vector_by_label(
                raw_results.get("max_api_requests_in_flight", []), "phase"
            ),
            "max_provider_origins_in_flight": _scalar(
                raw_results.get("max_provider_origins_in_flight", [])
            ),
            "max_provider_rate_budget_utilization_ratio": _scalar(
                raw_results.get("max_provider_rate_budget_utilization_ratio", [])
            ),
        },
        "assessment": {
            "p95_target_seconds": _P95_TARGET_SECONDS,
            "p95_target_met": p95 < _P95_TARGET_SECONDS if p95 is not None else None,
            "protection_threshold_seconds": _PROTECTION_THRESHOLD_SECONDS,
            "threshold_change_allowed": False,
            "threshold_change_blocked_by": [
                "pfSense CPU evidence",
                "pfSense RAM evidence",
                "PHP-FPM worker evidence",
                "FastCGI queue evidence",
            ],
        },
        "warnings": warnings,
    }


def collect_baseline(
    prometheus_url: str,
    *,
    window: str = _DEFAULT_WINDOW,
    timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    fetch_json: JsonFetcher = _default_fetch_json,
) -> dict[str, Any]:
    """Collect the passive baseline using only Prometheus query API calls."""
    queries = build_queries(window)
    raw_results = {
        name: query_prometheus(
            prometheus_url,
            promql,
            timeout=timeout,
            fetch_json=fetch_json,
        )
        for name, promql in queries.items()
    }
    return summarize_results(raw_results, window=window)


def _write_report(report: dict[str, Any], output: str | None) -> None:
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if output is None:
        sys.stdout.write(serialized)
        return
    Path(output).write_text(serialized, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Collect passive pfSense p95/p99 and protection evidence from "
            "Prometheus without issuing pfREST requests."
        )
    )
    parser.add_argument(
        "--prometheus-url",
        default=os.getenv("HOMELAB_PROMETHEUS_URL", ""),
        help="Prometheus base URL; defaults to HOMELAB_PROMETHEUS_URL.",
    )
    parser.add_argument("--window", default=_DEFAULT_WINDOW)
    parser.add_argument("--timeout", type=float, default=_DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--output",
        help="Optional JSON output path; stdout by default.",
    )
    args = parser.parse_args(argv)

    try:
        report = collect_baseline(
            args.prometheus_url,
            window=args.window,
            timeout=args.timeout,
        )
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        print(f"pfSense baseline collection failed: {exc}", file=sys.stderr)
        return 1

    _write_report(report, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
