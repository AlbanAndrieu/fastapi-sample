"""Merge the curated homelab catalog with live TrueNAS application data."""

from __future__ import annotations

import logging
import re
from typing import Any

import requests
from fastapi import APIRouter, Response

from nabla.integrations.truenas_apps import get_truenas_apps_json

router = APIRouter()
logger = logging.getLogger(__name__)

REFERENCE_URL = "https://www.albanandrieu.com/homelab-services.json"


def _normalized_name(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _reference_indexes(
    services: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, object], dict[str, Any]]]:
    by_name = {_normalized_name(service.get("name")): service for service in services}
    by_name_port = {(_normalized_name(service.get("name")), service.get("internalPort")): service for service in services}
    return by_name, by_name_port


def merge_services(
    reference_services: list[dict[str, Any]],
    truenas_services: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge curated metadata with live app state, containers and port mappings."""
    by_name, by_name_port = _reference_indexes(reference_services)
    merged: list[dict[str, Any]] = []
    used_reference_ids: set[int] = set()

    for live in truenas_services:
        name = _normalized_name(live.get("name"))
        reference = by_name_port.get((name, live.get("internalPort"))) or by_name.get(name)
        service = dict(reference or {})
        service.update(live)

        # A curated UI port is more useful than an arbitrary first Docker port,
        # but only retain it when TrueNAS confirms that it is currently published.
        if reference and reference.get("internalPort") in live.get("hostPorts", []):
            service["internalPort"] = reference["internalPort"]
        merged.append(service)
        if reference:
            used_reference_ids.add(id(reference))

    merged.extend(dict(reference) for reference in reference_services if id(reference) not in used_reference_ids)
    return merged


@router.get("/internal/services.json", response_model=None)
def merged_services() -> dict[str, Any] | Response:
    logger.info("Fetching reference services from master JSON...")
    try:
        response = requests.get(REFERENCE_URL, timeout=15)
        response.raise_for_status()
        reference_json = response.json()
    except (requests.RequestException, ValueError) as exc:
        return Response(f"Failed to fetch reference JSON: {exc}", status_code=502)

    try:
        truenas_json = get_truenas_apps_json()
    except Exception as exc:
        logger.exception("Failed to fetch TrueNAS apps")
        return Response(f"Failed to fetch TrueNAS apps: {exc}", status_code=502)

    return {
        "version": 2,
        "services": merge_services(
            reference_json.get("services", []),
            truenas_json.get("services", []),
        ),
    }
