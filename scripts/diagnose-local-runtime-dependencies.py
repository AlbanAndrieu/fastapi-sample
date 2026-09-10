#!/usr/bin/env python3
"""Normalize the cached FastAPI health-board into the six P0 runtime dependencies.

This helper deliberately does not call TrueNAS, pfSense, Cloudflare, Prometheus,
Sentry or Pyroscope directly. It requests the FastAPI health board and derives a
single operator matrix from evidence the runtime already collected.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

_DEFAULT_BASE_URL = "http://172.17.0.24:8091"
_DEFAULT_WAIT_SECONDS = 50.0
_POLL_SECONDS = 2.0
_DEPENDENCY_ORDER = (
    "truenas",
    "pfsense",
    "cloudflare",
    "prometheus",
    "sentry",
    "pyroscope",
)


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _bool_or_none(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _configured(check: dict[str, Any]) -> bool | None:
    explicit = _bool_or_none(check.get("configured"))
    if explicit is not None:
        return explicit
    if check.get("skipped") is True:
        reason = str(check.get("reason") or "").lower()
        if "not configured" in reason or "disabled" in reason or "empty" in reason:
            return False
    return True if check else None


def _error_stage(check: dict[str, Any]) -> str | None:
    for key in ("failure_stage", "configuration_stage", "error_kind"):
        value = str(check.get(key) or "").strip()
        if value:
            return value
    return None


def _auth_from_http(check: dict[str, Any]) -> bool | None:
    status = check.get("http_status")
    if not isinstance(status, int):
        return None
    if status in {401, 403}:
        return False
    if 200 <= status < 400:
        return True
    return None


def _common(check: dict[str, Any]) -> dict[str, Any]:
    return {
        "configured": _configured(check),
        "reachable": _bool_or_none(check.get("reachable")),
        "authenticated": None,
        "application_result": None,
        "stale": check.get("stale") is True,
        "error_stage": _error_stage(check),
        "error_kind": str(check.get("error_kind") or "").strip() or None,
        "error": str(check.get("error") or check.get("reason") or "").strip() or None,
        "evidence_complete": False,
    }


def _truenas(snapshot: dict[str, Any]) -> dict[str, Any]:
    homelab = _mapping(snapshot.get("homelab"))
    truenas = _mapping(homelab.get("truenas"))
    api = _mapping(truenas.get("api"))
    row = _common(api or truenas)
    row["configured"] = _configured(api or truenas)
    row["reachable"] = _bool_or_none(api.get("reachable"))
    apps = api.get("apps")
    app_count = len(apps) if isinstance(apps, list) else None
    if row["reachable"] is True and app_count is not None:
        row["authenticated"] = True
    elif row["error_stage"] == "authentication":
        row["authenticated"] = False
    row["application_result"] = {
        "kind": "truenas_app_inventory",
        "app_count": app_count,
        "state": truenas.get("state"),
        "path_mode": _mapping(truenas.get("diagnostics")).get("path_mode"),
    }
    row["stale"] = row["stale"] or _mapping(homelab.get("probe_cache")).get("stale") is True
    row["evidence_complete"] = bool(
        row["configured"] is True and row["reachable"] is True and row["authenticated"] is True and app_count is not None and app_count > 0 and not row["stale"],
    )
    return row


def _healthz_check(snapshot: dict[str, Any], name: str) -> dict[str, Any]:
    healthz = _mapping(snapshot.get("healthz"))
    return _mapping(_mapping(healthz.get("checks")).get(name))


def _pfsense(snapshot: dict[str, Any]) -> dict[str, Any]:
    check = _healthz_check(snapshot, "pfsense")
    row = _common(check)
    row["authenticated"] = _auth_from_http(check)
    row["application_result"] = {
        "kind": "pfsense_version_api",
        "path": check.get("path"),
        "http_status": check.get("http_status"),
        "credential_mode": check.get("credential_mode"),
    }
    row["evidence_complete"] = bool(
        row["configured"] is True and row["reachable"] is True and row["authenticated"] is True and not row["stale"],
    )
    return row


def _cloudflare(snapshot: dict[str, Any]) -> dict[str, Any]:
    check = _healthz_check(snapshot, "cloudflare")
    row = _common(check)
    row["reachable"] = _bool_or_none(check.get("api_reachable"))
    row["authenticated"] = _auth_from_http(check)
    if row["authenticated"] is None and check.get("status_confirmed") is True and row["reachable"] is True:
        row["authenticated"] = True
    row["application_result"] = {
        "kind": "cloudflare_tunnel_inventory",
        "status_confirmed": check.get("status_confirmed"),
        "tunnel_count": check.get("tunnel_count"),
        "healthy_tunnels": check.get("healthy_tunnels"),
        "unhealthy_tunnels": check.get("unhealthy_tunnels"),
    }
    row["evidence_complete"] = bool(
        row["configured"] is True and row["reachable"] is True and row["authenticated"] is True and check.get("status_confirmed") is True and not row["stale"],
    )
    return row


def _prometheus(snapshot: dict[str, Any]) -> dict[str, Any]:
    metrics = _mapping(snapshot.get("platform_metrics"))
    row = _common(metrics)
    state = str(metrics.get("state") or "unknown")
    configured = _bool_or_none(metrics.get("configured"))
    row["configured"] = configured
    if configured is False:
        row["reachable"] = None
    elif state == "telemetry_unavailable":
        row["reachable"] = False
    elif state in {"healthy", "degraded"}:
        row["reachable"] = True
    summary = _mapping(metrics.get("summary"))
    row["application_result"] = {
        "kind": "prometheus_recording_rules",
        "state": state,
        "signals_available": summary.get("signals_available"),
        "signals_total": summary.get("signals_total"),
        "telemetry_up": summary.get("telemetry_up"),
        "telemetry_total": summary.get("telemetry_total"),
    }
    row["error_stage"] = "query" if metrics.get("error_kind") == "query_failed" else row["error_stage"]
    row["evidence_complete"] = bool(
        configured is True and row["reachable"] is True and isinstance(summary.get("signals_available"), int) and summary.get("signals_available", 0) > 0,
    )
    return row


def _sentry(snapshot: dict[str, Any]) -> dict[str, Any]:
    check = _healthz_check(snapshot, "sentry")
    row = _common(check)
    row["application_result"] = {
        "kind": "dsn_socket_only",
        "probe": check.get("probe"),
        "target": check.get("target"),
    }
    # A socket probe does not prove Sentry API auth or event ingestion.
    row["evidence_complete"] = False
    return row


def _pyroscope(snapshot: dict[str, Any]) -> dict[str, Any]:
    check = _healthz_check(snapshot, "pyroscope")
    row = _common(check)
    row["application_result"] = {
        "kind": "readiness_only",
        "path": check.get("path"),
        "http_status": check.get("http_status"),
        "url": check.get("url"),
    }
    # Readiness alone does not prove fastapi-sample profile data can be queried.
    row["evidence_complete"] = False
    return row


def build_report(snapshot: dict[str, Any]) -> dict[str, Any]:
    dependencies = {
        "truenas": _truenas(snapshot),
        "pfsense": _pfsense(snapshot),
        "cloudflare": _cloudflare(snapshot),
        "prometheus": _prometheus(snapshot),
        "sentry": _sentry(snapshot),
        "pyroscope": _pyroscope(snapshot),
    }
    gaps = [name for name in _DEPENDENCY_ORDER if not dependencies[name]["evidence_complete"]]
    return {
        "schema_version": 1,
        "snapshot_state": snapshot.get("state"),
        "snapshot_generated_at": snapshot.get("generated_at"),
        "snapshot_age_seconds": snapshot.get("age_seconds"),
        "dependencies": dependencies,
        "evidence_complete": not gaps,
        "evidence_gaps": gaps,
    }


def _fetch_json(url: str, diagnostics_key: str | None) -> dict[str, Any]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RuntimeError("health-board URL must use http:// or https:// with a hostname")
    headers = {"Accept": "application/json", "Cache-Control": "no-cache"}
    if diagnostics_key:
        headers["X-Diagnostics-Key"] = diagnostics_key
    request = Request(url, headers=headers)  # noqa: S310 - URL restricted to HTTP(S) above
    try:
        with urlopen(request, timeout=8.0) as response:  # noqa: S310 - validated HTTP(S) request
            payload = json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"health-board returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"health-board transport failed: {exc.reason}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("health-board returned an unexpected payload")
    return payload


def fetch_converged_snapshot(base_url: str, diagnostics_key: str | None, wait_seconds: float) -> dict[str, Any]:
    endpoint = f"{base_url.rstrip('/')}/api/health-board"
    _fetch_json(f"{endpoint}?refresh=true", diagnostics_key)
    deadline = time.monotonic() + max(0.0, wait_seconds)
    latest: dict[str, Any] = {}
    while True:
        latest = _fetch_json(endpoint, diagnostics_key)
        if latest.get("state") != "pending" and latest.get("refreshing") is not True:
            return latest
        if time.monotonic() >= deadline:
            return latest
        time.sleep(_POLL_SECONDS)


def _fmt(value: object) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    if value is None:
        return "-"
    return str(value)


def print_table(report: dict[str, Any]) -> None:
    dependencies = _mapping(report.get("dependencies"))
    print("FastAPI local runtime dependency evidence")
    print(
        f"snapshot={report.get('snapshot_state')} age={report.get('snapshot_age_seconds')}s generated_at={report.get('snapshot_generated_at')}",
    )
    print()
    print(f"{'dependency':<12} {'configured':<10} {'reachable':<10} {'auth':<6} {'stale':<6} {'complete':<9} error_stage")
    for name in _DEPENDENCY_ORDER:
        row = _mapping(dependencies.get(name))
        print(
            f"{name:<12} {_fmt(row.get('configured')):<10} "
            f"{_fmt(row.get('reachable')):<10} {_fmt(row.get('authenticated')):<6} "
            f"{_fmt(row.get('stale')):<6} {_fmt(row.get('evidence_complete')):<9} "
            f"{_fmt(row.get('error_stage'))}",
        )
    gaps = report.get("evidence_gaps") or []
    print()
    if gaps:
        print("Evidence gaps: " + ", ".join(str(value) for value in gaps))
    else:
        print("✅ all six dependency evidence contracts are complete")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default=os.getenv("FASTAPI_RUNTIME_URL", _DEFAULT_BASE_URL),
        help="FastAPI runtime base URL (default: %(default)s)",
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=_DEFAULT_WAIT_SECONDS,
        help="maximum wait for one health-board refresh",
    )
    parser.add_argument("--json", action="store_true", help="print normalized JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    diagnostics_key = os.getenv("DIAGNOSTICS_ACCESS_KEY") or None
    try:
        snapshot = fetch_converged_snapshot(args.url, diagnostics_key, args.wait_seconds)
        report = build_report(snapshot)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_table(report)
    return 0 if report["evidence_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
