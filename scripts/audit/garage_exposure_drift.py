#!/usr/bin/env python3
"""Reconcile homelab exposure with fresh, sourced, sanitized observations.

The tool is offline and does not discover routes or probe hosts. Inferences
never equate Cloudflare edge reachability with anonymous origin access.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

LAYERS = (
    "public_dns",
    "cloudflare_tunnel",
    "cloudflare_access",
    "pfsense_nat_haproxy",
    "traefik",
    "outside_in_origin",
)
SOURCES = {
    "public_dns": frozenset({"dns_lookup"}),
    "cloudflare_tunnel": frozenset({"cloudflare_api"}),
    "cloudflare_access": frozenset({"cloudflare_api", "outside_in"}),
    "pfsense_nat_haproxy": frozenset({"pfsense_config"}),
    "traefik": frozenset({"traefik_config"}),
    "outside_in_origin": frozenset({"outside_in"}),
}
STATUSES = frozenset({"matched", "drift", "observed", "unknown"})


def _items(document: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(document, list):
        items = document
    elif isinstance(document, dict):
        items = document.get(key)
    else:
        raise ValueError("Expected a JSON array or object")
    if not isinstance(items, list) or any(not isinstance(row, dict) for row in items):
        raise ValueError(f"{key} must be an array of objects")
    return items


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("observed_at must be an ISO-8601 timestamp")
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("observed_at must be an ISO-8601 timestamp") from exc
    if instant.utcoffset() is None:
        raise ValueError("observed_at must include a timezone")
    return instant.astimezone(timezone.utc)


def _clean_evidence(
    entry: Any,
    *,
    layer: str,
    now: datetime,
    max_age: timedelta,
) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise ValueError(f"{layer} evidence must be an object")
    status = entry.get("status", "unknown")
    if not isinstance(status, str) or status not in STATUSES:
        raise ValueError(f"Invalid evidence status for {layer}")
    if status == "unknown":
        return {"status": "unknown"}

    source = entry.get("source")
    if not isinstance(source, str) or source not in SOURCES[layer]:
        raise ValueError(f"Untrusted evidence source for {layer}")
    observed_at = _timestamp(entry.get("observed_at"))
    # Keep clock-skew tolerance explicit; never present a future observation as fact.
    age = now - observed_at
    if age < timedelta(minutes=-5) or age > max_age:
        return {"status": "unknown", "reason": "stale_or_future_evidence"}

    clean: dict[str, Any] = {
        "status": status,
        "source": source,
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
    }
    http_status = entry.get("http_status")
    if type(http_status) is int and 100 <= http_status <= 599:
        clean["http_status"] = http_status
    # Never pass through URL, Location, CF token, cookies or free-form notes.
    return clean


def reconcile(
    declared: Any,
    observed: Any,
    *,
    now: datetime | None = None,
    max_age: timedelta = timedelta(hours=24),
) -> dict[str, Any]:
    """Compute conservative exposure findings from independent layer evidence."""
    clock = now or datetime.now(timezone.utc)
    if clock.utcoffset() is None:
        raise ValueError("now must include a timezone")
    if not timedelta(0) < max_age <= timedelta(days=7):
        raise ValueError("max_age must be between 0 and 7 days")
    clock = clock.astimezone(timezone.utc)
    services = _items(declared, "services")
    evidence = _items(observed, "observations")
    by_id: dict[str, dict[str, Any]] = {}
    for row in evidence:
        service_id = row.get("service_id")
        if not isinstance(service_id, str) or not service_id or service_id in by_id:
            raise ValueError("Observation IDs must be unique, nonempty strings")
        by_id[service_id] = row

    output = []
    seen: set[str] = set()
    for service in services:
        service_id = service.get("id", service.get("service_id"))
        if not isinstance(service_id, str) or not service_id or service_id in seen:
            raise ValueError("Service IDs must be unique, nonempty strings")
        seen.add(service_id)
        external = service.get("external")
        if type(external) is not bool:
            raise ValueError(f"external must be boolean for {service_id}")
        evidence_layers = by_id.get(service_id, {}).get("layers", {})
        if not isinstance(evidence_layers, dict):
            raise ValueError(f"layers must be an object for {service_id}")
        unexpected = set(evidence_layers) - set(LAYERS)
        if unexpected:
            raise ValueError(f"Unknown evidence layer for {service_id}")
        layers = {
            name: _clean_evidence(
                evidence_layers.get(name, {}), layer=name, now=clock, max_age=max_age
            )
            for name in LAYERS
        }
        private = not external
        route_drift = private and any(
            layers[name]["status"] == "drift"
            for name in (
                "public_dns",
                "cloudflare_tunnel",
                "pfsense_nat_haproxy",
                "traefik",
                "outside_in_origin",
            )
        )
        # An outside-in Access response is edge evidence, not origin verification.
        edge_visible = any(
            layers[name]["status"] in {"observed", "drift"}
            for name in ("cloudflare_access", "cloudflare_tunnel", "outside_in_origin")
        )
        if route_drift:
            assessment = "confirmed_drift"
        elif private and edge_visible:
            assessment = "requires_review"
        elif all(layer["status"] == "unknown" for layer in layers.values()):
            assessment = "unknown"
        else:
            assessment = "no_confirmed_drift"
        output.append(
            {
                "service_id": service_id,
                "expected_external": external,
                "layers": layers,
                "exposure_assessment": assessment,
                "origin_anonymously_accessible": None,
            }
        )

    unexpected_ids = sorted(set(by_id) - seen)
    if unexpected_ids:
        raise ValueError("Observation references unknown service IDs")
    revision = declared.get("catalog_revision") if isinstance(declared, dict) else None
    return {
        "catalog_revision": (
            revision if isinstance(revision, str) and revision else "unknown"
        ),
        "services": sorted(output, key=lambda item: item["service_id"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--declared", type=Path, required=True)
    parser.add_argument("--observed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of", help="ISO-8601 reference time for offline replay")
    parser.add_argument("--max-age-hours", type=float, default=24.0)
    args = parser.parse_args()
    if args.output.resolve() in (args.declared.resolve(), args.observed.resolve()):
        parser.error("output must differ from input paths")
    if not 0 < args.max_age_hours <= 168:
        parser.error("--max-age-hours must be in (0, 168]")
    report = reconcile(
        json.loads(args.declared.read_text(encoding="utf-8")),
        json.loads(args.observed.read_text(encoding="utf-8")),
        now=_timestamp(args.as_of) if args.as_of else None,
        max_age=timedelta(hours=args.max_age_hours),
    )
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
