#!/usr/bin/env python3
"""Reconcile declared homelab exposure with sanitized observations (offline).

No network calls, credentials, raw headers or origin URLs are read or emitted.
Evidence is limited to explicitly enumerated metadata fields.
"""
from __future__ import annotations

import argparse
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
STATUSES = frozenset(("matched", "drift", "observed", "unknown"))


def _items(document: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(document, list):
        items = document
    elif isinstance(document, dict):
        items = document.get(key, [])
    else:
        raise ValueError("Expected a JSON array or object")
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError(f"{key} must be an array of objects")
    return items


def reconcile(declared: Any, observed: Any) -> dict[str, Any]:
    """Return a deterministic report; missing evidence is *always* unknown."""
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
        private = service.get("external") is False
        if not isinstance(service.get("external"), bool):
            raise ValueError(f"external must be boolean for {service_id}")
        source = by_id.get(service_id, {})
        observations = source.get("layers", {})
        if not isinstance(observations, dict):
            raise ValueError(f"layers must be an object for {service_id}")
        layers: dict[str, dict[str, Any]] = {}
        for name in LAYERS:
            entry = observations.get(name, {})
            if not isinstance(entry, dict):
                raise ValueError(f"{name} must be an object for {service_id}")
            status = entry.get("status", "unknown")
            if status not in STATUSES:
                raise ValueError(f"Invalid status for {service_id}/{name}")
            # Allowlist only; never copy credentials, arbitrary URLs or raw headers.
            clean: dict[str, Any] = {"status": status}
            http_status = entry.get("http_status")
            if type(http_status) is int and 100 <= http_status <= 599:
                clean["http_status"] = http_status
            layers[name] = clean

        access = layers["cloudflare_access"]
        public_edge = access["status"] == "observed" and access.get("http_status") in (301, 302, 303, 307, 308)
        route_drift = private and any(
            layers[name]["status"] == "drift"
            for name in ("public_dns", "cloudflare_tunnel", "pfsense_nat_haproxy", "traefik", "outside_in_origin")
        )
        output.append({
            "service_id": service_id,
            "expected_external": not private,
            "layers": layers,
            "exposure_assessment": (
                "confirmed_drift" if route_drift else
                "requires_review" if private and public_edge else
                "unknown" if all(layer["status"] == "unknown" for layer in layers.values()) else
                "no_confirmed_drift"
            ),
            "origin_anonymously_accessible": None,
        })
    unknown = sorted(set(by_id) - seen)
    if unknown:
        raise ValueError("Observations reference unknown service IDs: " + ", ".join(unknown))
    revision = declared.get("catalog_revision") if isinstance(declared, dict) else None
    return {"catalog_revision": revision if isinstance(revision, str) else "unknown",
            "services": sorted(output, key=lambda item: item["service_id"])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--declared", type=Path, required=True)
    parser.add_argument("--observed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() in (args.declared.resolve(), args.observed.resolve()):
        parser.error("output must differ from input paths")
    report = reconcile(json.loads(args.declared.read_text(encoding="utf-8")),
                       json.loads(args.observed.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
