#!/usr/bin/env python3
"""Normalize the cached FastAPI health-board into the P0 runtime dependencies.

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
    "postgres",
    "redis",
    "gatus",
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


def _application_ok_from_http(check: dict[str, Any]) -> bool | None:
    explicit = _bool_or_none(check.get("application_ok"))
    if explicit is not None:
        return explicit
    status = check.get("http_status")
    if not isinstance(status, int):
        return None
    return 200 <= status < 400


def _transport_reachable(check: dict[str, Any]) -> bool | None:
    """An HTTP response proves transport even when the application returns 4xx/5xx."""
    if isinstance(check.get("http_status"), int):
        return True
    return _bool_or_none(check.get("reachable"))


def _state(
    *,
    configured: bool | None,
    reachable: bool | None,
    application_ok: bool | None,
    complete: bool,
    warning: bool = False,
) -> str:
    if configured is False:
        return "configuration_required"
    if warning:
        return "warning"
    if reachable is False:
        return "unreachable"
    if application_ok is False:
        return "application_error"
    if complete:
        return "ok"
    return "evidence_incomplete"


def _common(check: dict[str, Any]) -> dict[str, Any]:
    return {
        "configured": _configured(check),
        "reachable": _transport_reachable(check),
        "authenticated": None,
        "application_ok": _application_ok_from_http(check),
        "application_result": None,
        "stale": check.get("stale") is True,
        "error_stage": _error_stage(check),
        "error_kind": str(check.get("error_kind") or "").strip() or None,
        "error": str(check.get("error") or check.get("reason") or "").strip() or None,
        "operational_state": "evidence_incomplete",
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
    row["application_ok"] = (app_count > 0) if row["reachable"] is True and app_count is not None else None
    row["application_result"] = {
        "kind": "truenas_app_inventory",
        "app_count": app_count,
        "state": truenas.get("state"),
        "path_mode": _mapping(truenas.get("diagnostics")).get("path_mode"),
    }
    row["stale"] = row["stale"] or _mapping(homelab.get("probe_cache")).get("stale") is True
    row["evidence_complete"] = bool(
        row["configured"] is True and row["reachable"] is True and row["authenticated"] is True and row["application_ok"] is True and not row["stale"],
    )
    row["operational_state"] = _state(
        configured=row["configured"],
        reachable=row["reachable"],
        application_ok=row["application_ok"],
        complete=row["evidence_complete"],
    )
    return row


def _healthz_check(snapshot: dict[str, Any], name: str) -> dict[str, Any]:
    healthz = _mapping(snapshot.get("healthz"))
    return _mapping(_mapping(healthz.get("checks")).get(name))


def _pfsense(snapshot: dict[str, Any]) -> dict[str, Any]:
    check = _healthz_check(snapshot, "pfsense")
    row = _common(check)
    row["reachable"] = _transport_reachable(check)
    row["authenticated"] = _bool_or_none(check.get("api_authenticated"))
    if row["authenticated"] is None:
        row["authenticated"] = _bool_or_none(check.get("authenticated"))
    if row["authenticated"] is None:
        row["authenticated"] = _auth_from_http(check)
    row["application_ok"] = _application_ok_from_http(check)
    row["application_result"] = {
        "kind": "pfsense_version_api",
        "path": check.get("path"),
        "http_status": check.get("http_status"),
        "credential_mode": check.get("credential_mode"),
        "application_ok": row["application_ok"],
        "application_result": check.get("application_result"),
    }
    row["evidence_complete"] = bool(
        row["configured"] is True and row["reachable"] is True and row["authenticated"] is True and row["application_ok"] is True and not row["stale"],
    )
    row["operational_state"] = _state(
        configured=row["configured"],
        reachable=row["reachable"],
        application_ok=row["application_ok"],
        complete=row["evidence_complete"],
    )
    return row


def _cloudflare(snapshot: dict[str, Any]) -> dict[str, Any]:
    check = _healthz_check(snapshot, "cloudflare")
    row = _common(check)
    row["reachable"] = _bool_or_none(check.get("api_reachable"))
    row["authenticated"] = _auth_from_http(check)
    if row["authenticated"] is None and check.get("status_confirmed") is True and row["reachable"] is True:
        row["authenticated"] = True
    status_confirmed = check.get("status_confirmed") is True
    row["application_ok"] = status_confirmed if row["reachable"] is True else None
    row["application_result"] = {
        "kind": "cloudflare_tunnel_inventory",
        "status_confirmed": check.get("status_confirmed"),
        "tunnel_count": check.get("tunnel_count"),
        "healthy_tunnels": check.get("healthy_tunnels"),
        "unhealthy_tunnels": check.get("unhealthy_tunnels"),
    }
    row["evidence_complete"] = bool(
        row["configured"] is True and row["reachable"] is True and row["authenticated"] is True and status_confirmed and not row["stale"],
    )
    unconfirmed_warning = bool(
        row["reachable"] is True and row["authenticated"] is True and not status_confirmed,
    )
    row["operational_state"] = _state(
        configured=row["configured"],
        reachable=row["reachable"],
        application_ok=row["application_ok"],
        complete=row["evidence_complete"],
        warning=unconfirmed_warning,
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
        row["application_ok"] = None
        row["error_stage"] = "configuration"
        row["error_kind"] = "not_configured"
        row["error"] = "HOMELAB_PROMETHEUS_URL is not configured in this FastAPI runtime"
    elif state == "telemetry_unavailable":
        row["reachable"] = False
        row["application_ok"] = False
    elif state in {"healthy", "degraded"}:
        row["reachable"] = True
        row["application_ok"] = True
    summary = _mapping(metrics.get("summary"))
    row["application_result"] = {
        "kind": "prometheus_recording_rules",
        "state": state,
        "required_setting": "HOMELAB_PROMETHEUS_URL",
        "signals_available": summary.get("signals_available"),
        "signals_total": summary.get("signals_total"),
        "telemetry_up": summary.get("telemetry_up"),
        "telemetry_total": summary.get("telemetry_total"),
    }
    row["error_stage"] = "query" if metrics.get("error_kind") == "query_failed" else row["error_stage"]
    row["evidence_complete"] = bool(
        configured is True
        and row["reachable"] is True
        and row["application_ok"] is True
        and isinstance(summary.get("signals_available"), int)
        and summary.get("signals_available", 0) > 0,
    )
    row["operational_state"] = _state(
        configured=row["configured"],
        reachable=row["reachable"],
        application_ok=row["application_ok"],
        complete=row["evidence_complete"],
    )
    return row


def _sentry(snapshot: dict[str, Any]) -> dict[str, Any]:
    check = _healthz_check(snapshot, "sentry")
    row = _common(check)
    # A DSN socket never proves event ingestion; accept only explicit cached E2E evidence.
    ingestion = _mapping(check.get("ingestion_evidence"))
    row["application_ok"] = _bool_or_none(ingestion.get("persisted"))
    row["application_result"] = {
        "kind": "sentry_ingestion" if ingestion else "dsn_socket_only",
        "ingestion_confirmed": row["application_ok"],
        "probe": check.get("probe"),
        "target": check.get("target"),
    }
    row["evidence_complete"] = bool(
        row["configured"] is True and row["reachable"] is True and row["application_ok"] is True and ingestion.get("fresh") is True and not row["stale"],
    )
    row["operational_state"] = _state(
        configured=row["configured"],
        reachable=row["reachable"],
        application_ok=row["application_ok"],
        complete=row["evidence_complete"],
    )
    return row


def _pyroscope(snapshot: dict[str, Any]) -> dict[str, Any]:
    check = _healthz_check(snapshot, "pyroscope")
    row = _common(check)
    status = check.get("http_status")
    readiness_path = check.get("path") in {"/ready", "/health"}
    readiness_ok = type(status) is int and 200 <= status < 300 and readiness_path
    row["reachable"] = _transport_reachable(check)
    row["application_ok"] = readiness_ok if readiness_path and type(status) is int else None
    row["application_result"] = {
        "kind": "readiness_only",
        "path": check.get("path"),
        "http_status": status,
        "url": check.get("url"),
        "readiness_ok": row["application_ok"],
    }
    row["evidence_complete"] = False
    row["operational_state"] = _state(
        configured=row["configured"],
        reachable=row["reachable"],
        application_ok=row["application_ok"],
        complete=False,
    )
    return row


def _component(snapshot: dict[str, Any], name: str) -> dict[str, Any]:
    """Read existing component evidence; never open an extra DB or Redis session."""
    components = _mapping(_mapping(snapshot.get("homelab")).get("components"))
    check = _mapping(components.get(name))
    row = _common(check)
    row["reachable"] = _transport_reachable(check)
    # A reachable TCP socket is not proof that PostgreSQL/Redis accepted a
    # command or authenticated a client. Keep missing application proof unknown.
    proof = _mapping(check.get("application_evidence"))
    proof_kind = "sql_select_1" if name == "postgres" else "redis_ping"
    evidence_valid = proof.get("kind") == proof_kind and proof.get("authenticated") is True
    explicit_ok = _bool_or_none(check.get("application_ok"))
    row["application_ok"] = explicit_ok if explicit_ok is False else _bool_or_none(proof.get("ok")) if evidence_valid else None
    row["application_result"] = {
        "kind": "cached_component",
        "proof_kind": proof.get("kind"),
        "command_authenticated": proof.get("authenticated") if evidence_valid else None,
        "state": check.get("state"),
        "status": check.get("status"),
    }
    row["evidence_complete"] = bool(
        check and row["configured"] is True and row["reachable"] is True and row["application_ok"] is True and not row["stale"],
    )
    row["operational_state"] = _state(
        configured=row["configured"],
        reachable=row["reachable"],
        application_ok=row["application_ok"],
        complete=row["evidence_complete"],
    )
    return row


def _gatus(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Gatus is diagnostic-only and cannot override public exposure evidence."""
    metrics = _mapping(snapshot.get("platform_metrics"))
    synthetic = _mapping(metrics.get("synthetic_probes"))
    comparison = _mapping(snapshot.get("internal_probe_comparison"))
    delegation = _mapping(snapshot.get("internal_probe_delegation"))
    row = _common(synthetic)
    row["configured"] = _bool_or_none(metrics.get("configured"))
    value = synthetic.get("gatus_up")
    row["reachable"] = value == 1.0 if type(value) in (int, float) else None
    # Prometheus up confirms a scraped target, not Gatus endpoint history.
    coverage = synthetic.get("state") == "observed" and comparison.get("state") == "observed"
    row["application_ok"] = True if row["reachable"] is True and coverage else None
    row["application_result"] = {
        "kind": "gatus_via_prometheus",
        "coverage_observed": coverage,
        "gatus_source": synthetic.get("gatus_source"),
        "scope": "truenas_internal_only",
        "service_count": synthetic.get("service_count"),
        "comparable": comparison.get("comparable"),
        "matched": comparison.get("matched"),
        "mismatched": comparison.get("mismatched"),
        "missing_gatus": comparison.get("missing_gatus"),
        "missing_gatus_ids": comparison.get("missing_gatus_ids", []),
        "missing_gatus_reasons": comparison.get("missing_gatus_reasons", {}),
        "conflicting_direct_ids": comparison.get("conflicting_direct_ids", []),
        "delegation_candidate": delegation.get("candidate"),
        "delegation_blockers": delegation.get("blockers"),
        "external_probes_preserved": True,
    }
    row["evidence_complete"] = bool(
        row["configured"] is True
        and row["reachable"] is True
        and synthetic.get("state") == "observed"
        and type(synthetic.get("service_count")) is int
        and synthetic["service_count"] > 0
        and comparison.get("state") == "observed"
        and not row["stale"],
    )
    row["operational_state"] = _state(
        configured=row["configured"],
        reachable=row["reachable"],
        application_ok=row["application_ok"],
        complete=row["evidence_complete"],
    )
    return row


def build_report(snapshot: dict[str, Any]) -> dict[str, Any]:
    dependencies = {
        "truenas": _truenas(snapshot),
        "pfsense": _pfsense(snapshot),
        "cloudflare": _cloudflare(snapshot),
        "prometheus": _prometheus(snapshot),
        "sentry": _sentry(snapshot),
        "pyroscope": _pyroscope(snapshot),
        "postgres": _component(snapshot, "postgres"),
        "redis": _component(snapshot, "redis"),
        "gatus": _gatus(snapshot),
    }
    gaps = [name for name in _DEPENDENCY_ORDER if not dependencies[name]["evidence_complete"]]
    snapshot_ready = snapshot.get("state") == "fresh" and snapshot.get("refreshing") is not True
    snapshot_fresh = snapshot_ready and snapshot.get("stale") is not True
    return {
        "schema_version": 2,
        "snapshot_state": snapshot.get("state"),
        "snapshot_generated_at": snapshot.get("generated_at"),
        "snapshot_age_seconds": snapshot.get("age_seconds"),
        "dependencies": dependencies,
        "evidence_complete": not gaps and snapshot_fresh,
        "snapshot_fresh": snapshot_fresh,
        "evidence_gaps": gaps,
    }


def basic_availability(report: dict[str, Any]) -> dict[str, str]:
    """Basic status uses cached reachability, never fabricated deep acceptance."""
    rows = _mapping(report.get("dependencies"))
    results: dict[str, str] = {}
    for name in _DEPENDENCY_ORDER:
        row = _mapping(rows.get(name))
        if row.get("configured") is False:
            status = "not_configured"
        elif row.get("reachable") is True:
            status = "reachable"
        elif row.get("reachable") is False:
            status = "unreachable"
        else:
            status = "unknown"
        results[name] = status
    return results


def print_basic_availability(report: dict[str, Any], *, color: bool = False) -> None:
    print("\n📡 Basic availability (transport only, NOT deep acceptance)")
    for name, status in basic_availability(report).items():
        label = {"reachable": "✅", "unreachable": "❌"}.get(status, "❔")
        if color:
            ansi = "\x1b[32m" if status == "reachable" else "\x1b[31m" if status == "unreachable" else "\x1b[33m"
            label = f"{ansi}{label}\x1b[0m"
        print(f"  {label} {name:<12} {status}")
    print("ℹ️ Deep evidence and security authorization are separate; see nabla-compose scripts/truenas/.")  # noqa: RUF001


def _fetch_json(url: str, diagnostics_key: str | None) -> dict[str, Any]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RuntimeError("health-board URL must use http:// or https:// with a hostname")
    headers = {"Accept": "application/json", "Cache-Control": "no-cache"}
    if diagnostics_key:
        headers["X-Diagnostics-Key"] = diagnostics_key
    request = Request(url, headers=headers)  # noqa: S310 - URL restricted to HTTP(S) above
    try:
        with urlopen(request, timeout=8.0) as response:  # nosec B310  # noqa: S310 - scheme validated above
            payload = json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"health-board returned HTTP {exc.code}") from exc
    except TimeoutError as exc:
        raise RuntimeError("health-board request timed out after 8 seconds") from exc
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


_STATE_STYLE = {
    "ok": ("✅", "\x1b[32m"),
    "warning": ("⚠️", "\x1b[33m"),
    "evidence_incomplete": ("❔", "\x1b[33m"),
    "configuration_required": ("⚙️", "\x1b[33m"),
    "unreachable": ("❌", "\x1b[31m"),
    "application_error": ("❌", "\x1b[31m"),
}


def _status_label(state: object, *, color: bool) -> str:
    value = str(state or "unknown")
    icon, ansi = _STATE_STYLE.get(value, ("❔", "\x1b[33m"))
    label = f"{icon} {value}"
    return f"{ansi}{label}\x1b[0m" if color else label


_GAP_GUIDANCE = {
    "truenas": "Inspect API inventory and observer privileges (APPS_READ); do not infer application failure when apps evidence is absent.",
    "pfsense": "Check authenticated /api/v2/system/version evidence from the TrueNAS observer; do not treat transport as authorization.",
    "pyroscope": "Restore HTTP readiness, then verify recent profile ingestion; check runtime UID/dataset permissions before restart.",
    "sentry": "DSN socket evidence is insufficient; verify a bounded event ID and downstream ingestion.",
    "postgres": "TCP is not application proof; inspect cached authenticated command health without extra probe fan-out.",
    "redis": "TCP is not application proof; inspect cached authenticated command health without extra probe fan-out.",
    "gatus": "Check Gatus HTTP/history and Prometheus gatus_up metrics internally; never replace outside-in checks.",
}
_DEFAULT_GAP_GUIDANCE = "Inspect existing runtime evidence, not an additional provider probe."


def _gap_extra(name: object, detail: dict[str, Any]) -> str:
    """Return bounded dependency-specific evidence appended to a gap line."""
    if name == "truenas":
        return f" apps={detail.get('app_count')}"
    if name != "gatus":
        return ""
    ids = detail.get("missing_gatus_ids")
    reasons = detail.get("missing_gatus_reasons")
    conflicts = detail.get("conflicting_direct_ids")
    extra = f" missing_ids={ids} reasons={reasons}" if ids else ""
    if conflicts:
        extra += f" conflicting_direct_ids={conflicts}"
    return extra


def _print_evidence_gap(name: object, dependencies: dict[str, Any], *, color: bool) -> None:
    row = _mapping(dependencies.get(name))
    state = row.get("operational_state")
    stage = row.get("error_stage") or row.get("error_kind") or "no_application_proof"
    detail = _mapping(row.get("application_result"))
    guidance = _GAP_GUIDANCE.get(name, _DEFAULT_GAP_GUIDANCE)
    extra = _gap_extra(name, detail)
    print(f"  {_status_label(state, color=color)} {name}: stage={stage}{extra}; {guidance}")


def print_table(report: dict[str, Any], *, color: bool = False) -> None:
    dependencies = _mapping(report.get("dependencies"))
    print("FastAPI local runtime dependency evidence")
    print(
        f"snapshot={report.get('snapshot_state')} age={report.get('snapshot_age_seconds')}s generated_at={report.get('snapshot_generated_at')}",
    )
    print()
    print(
        f"{'dependency':<12} {'configured':<10} {'transport':<10} {'auth':<6} {'app':<6} {'stale':<6} {'state':<22} error_stage",
    )
    for name in _DEPENDENCY_ORDER:
        row = _mapping(dependencies.get(name))
        decorated_state = _status_label(row.get("operational_state"), color=color)
        print(
            f"{name:<12} {_fmt(row.get('configured')):<10} "
            f"{_fmt(row.get('reachable')):<10} {_fmt(row.get('authenticated')):<6} "
            f"{_fmt(row.get('application_ok')):<6} {_fmt(row.get('stale')):<6} "
            f"{decorated_state} {_fmt(row.get('error_stage'))}",
        )
    gaps = report.get("evidence_gaps") or []
    print()
    if gaps:
        print("⚠️ Evidence gaps: " + ", ".join(str(value) for value in gaps))
        for name in gaps:
            _print_evidence_gap(name, dependencies, color=color)
    else:
        print("✅ all dependency evidence contracts are complete")


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
    parser.add_argument("--basic", action="store_true", help="report cached basic reachability without requiring deep evidence")
    parser.add_argument("--color", choices=("auto", "always", "never"), default="auto", help="ANSI color for text output")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="return 0 when the board is readable; still print all evidence gaps (no acceptance proof)",
    )
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
        color = args.color == "always" or (args.color == "auto" and sys.stdout.isatty() and "NO_COLOR" not in os.environ)
        if args.basic:
            print_basic_availability(report, color=color)
        else:
            print_table(report, color=color)
    return 0 if args.basic or args.report_only or report["evidence_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
