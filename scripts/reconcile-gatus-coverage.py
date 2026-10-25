#!/usr/bin/env python3
"""Reconcile Gatus declarations with a saved FastAPI snapshot without network I/O.

Prints monitor IDs only; never prints target URLs, credentials or tokens.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
PROTOCOLS = {"http": "HTTP", "https": "HTTPS", "tcp": "TCP"}
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_MONITORS = 256


def load_document(path: Path, *, as_yaml: bool) -> Any:
    """Read and parse bounded local data without executing YAML objects."""
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("input file exceeds size limit")
    content = path.read_text(encoding="utf-8")
    return yaml.safe_load(content) if as_yaml else json.loads(content)


def declared_checks(config: dict[str, Any]) -> tuple[list[dict[str, str]], list[str]]:
    """Extract canonical identifiers from Gatus endpoint declarations."""
    checks: list[dict[str, str]] = []
    warnings: list[str] = []
    endpoints = config.get("endpoints", [])
    if not isinstance(endpoints, list):
        raise ValueError("Gatus endpoints must be a list")
    if len(endpoints) > MAX_MONITORS:
        raise ValueError("too many Gatus endpoints")
    ids = set()
    for index, endpoint in enumerate(endpoints):
        if not isinstance(endpoint, dict):
            warnings.append(f"invalid_endpoint:{index}")
            continue
        labels = endpoint.get("extra-labels", {})
        if not isinstance(labels, dict):
            warnings.append(f"invalid_labels:{index}")
            continue
        service_id = labels.get("nabla_service_id")
        monitor_id = labels.get("nabla_monitor_id")
        if not isinstance(service_id, str) or not ID_RE.fullmatch(service_id):
            warnings.append(f"missing_canonical_service_id:{index}")
            continue
        if not isinstance(monitor_id, str) or not ID_RE.fullmatch(monitor_id):
            warnings.append(f"invalid_monitor_id:{index}")
            continue
        url = endpoint.get("url")
        scheme = url.split(":", 1)[0].lower() if isinstance(url, str) else ""
        protocol = PROTOCOLS.get(scheme)
        if protocol is None:
            warnings.append(f"unsupported_protocol:{monitor_id}")
            continue
        key = (monitor_id, service_id, protocol)
        if key in ids:
            warnings.append(f"duplicate_monitor:{monitor_id}")
            continue
        ids.add(key)
        checks.append({"monitor_id": monitor_id, "service_id": service_id, "protocol": protocol})
    return checks, warnings


def snapshot_state(snapshot: dict[str, Any] | None, now: datetime) -> tuple[str, dict[str, Any]]:
    """Do not classify successes or failures from stale/untrusted telemetry."""
    if not isinstance(snapshot, dict):
        return "not_provided", {}
    metrics = snapshot.get("platform_metrics", {})
    if not isinstance(metrics, dict):
        return "metrics_missing", {}
    try:
        timestamp = datetime.fromisoformat(str(metrics.get("generated_at")).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("missing timezone")
        age = (now - timestamp.astimezone(UTC)).total_seconds()
    except (ValueError, TypeError, OverflowError):
        return "timestamp_invalid", {}
    if not (-60 <= age <= 180):
        return "snapshot_stale", {}
    synthetic = metrics.get("synthetic_probes", {})
    if not isinstance(synthetic, dict):
        return "telemetry_missing", {}
    if synthetic.get("truncated") is True:
        return "truncated", {}
    if synthetic.get("gatus_up") != 1 or isinstance(synthetic.get("gatus_up"), bool):
        return "gatus_scrape_unverified", {}
    if synthetic.get("state") != "observed":
        return "rules_unverified", {}
    services = synthetic.get("services", {})
    if not isinstance(services, dict) or len(services) > MAX_MONITORS:
        return "invalid_services", {}
    return "observed", services


def reconcile(
    config: dict[str, Any], snapshot: dict[str, Any] | None, *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Correlate each declared monitor with a bounded protocol-level sample."""
    if not isinstance(config, dict):
        raise ValueError("invalid Gatus config")
    checks, warnings = declared_checks(config)
    state, services = snapshot_state(snapshot, now or datetime.now(UTC))
    groups: dict[str, list[dict[str, str]]] = {
        "up": [], "down": [], "no_sample": [], "unverified": []
    }
    for check in checks:
        service = services.get(check["service_id"], {})
        probe = service.get(check["protocol"], {}) if isinstance(service, dict) else {}
        success = probe.get("success") if isinstance(probe, dict) else None
        if state != "observed":
            outcome = "unverified"
        elif (isinstance(success, bool) or not isinstance(success, (int, float))
              or not math.isfinite(success) or success not in (0, 1)):
            outcome = "no_sample"
        elif success == 1:
            outcome = "up"
        else:
            outcome = "down"
        groups[outcome].append(check)
    configured = {(check["service_id"], check["protocol"]) for check in checks}
    unexpected: list[dict[str, str]] = []
    if state == "observed":
        for service_id, probes in services.items():
            if (not isinstance(service_id, str) or not ID_RE.fullmatch(service_id)
                    or not isinstance(probes, dict)):
                continue
            for protocol in sorted(set(probes) & set(PROTOCOLS.values())):
                if (service_id, protocol) not in configured:
                    unexpected.append({"service_id": service_id, "protocol": protocol})
    return {
        "state": state,
        "declared_count": len(checks),
        "observed_count": len(groups["up"]) + len(groups["down"]),
        "counts": {key: len(value) for key, value in groups.items()},
        "checks": groups,
        "unmatched_observed": unexpected[:MAX_MONITORS],
        "warnings": warnings,
        "note": "Declared monitors only; missing/stale samples never imply DOWN. No network probes executed.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="Local Gatus config.yml")
    parser.add_argument("--snapshot", type=Path, help="Saved authorized /api/health-board JSON")
    args = parser.parse_args()
    try:
        config = load_document(args.config, as_yaml=True)
        snapshot = load_document(args.snapshot, as_yaml=False) if args.snapshot else None
        result = reconcile(config, snapshot)
    except (OSError, ValueError, yaml.YAMLError, json.JSONDecodeError) as exc:
        parser.exit(2, f"Invalid local evidence: {type(exc).__name__}\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    complete = (result["state"] == "observed" and not result["checks"]["down"]
                and not result["checks"]["no_sample"] and not result["warnings"])
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
