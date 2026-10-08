"""Shared helpers for fixed, read-only Prometheus instant queries."""

from __future__ import annotations

import math
from typing import Any

import httpx


def safe_float(value: object) -> float | None:
    """Return a finite float or None for malformed/non-finite Prometheus values."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def vector_result(payload: object) -> list[dict[str, Any]]:
    """Return a validated Prometheus vector result, or an empty list."""
    if not isinstance(payload, dict) or payload.get("status") != "success":
        return []
    data = payload.get("data")
    if not isinstance(data, dict) or data.get("resultType") != "vector":
        return []
    result = data.get("result")
    if not isinstance(result, list):
        return []
    return [item for item in result if isinstance(item, dict)]


def sample_value(sample: dict[str, Any]) -> float | None:
    """Extract one finite numeric value from a Prometheus instant-vector sample."""
    raw = sample.get("value")
    if not isinstance(raw, list) or len(raw) != 2:
        return None
    return safe_float(raw[1])


async def query_vector(
    client: httpx.AsyncClient,
    expression: str,
) -> list[dict[str, Any]]:
    """Run one fixed Prometheus instant query and return its vector samples."""
    response = await client.get(
        "/api/v1/query",
        params={"query": expression},
        headers={"Accept": "application/json"},
    )
    response.raise_for_status()
    return vector_result(response.json())
