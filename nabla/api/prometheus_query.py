"""Shared helpers for fixed, read-only Prometheus instant and range queries."""

from __future__ import annotations

import math
from typing import Any

import httpx


def safe_float(value: object) -> float | None:
    """Return a finite float or None for malformed/non-finite Prometheus values."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
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
    # A Cloudflare Access 302 is not a successful Prometheus query, even
    # though raise_for_status() does not reject redirects.
    if 300 <= response.status_code < 400:
        raise httpx.HTTPStatusError(
            "Prometheus query redirected (possible Cloudflare Access)",
            request=response.request,
            response=response,
        )
    response.raise_for_status()
    payload = response.json()
    result = payload.get("data") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or payload.get("status") != "success"
        or not isinstance(result, dict)
        or result.get("resultType") != "vector"
        or not isinstance(result.get("result"), list)
    ):
        raise ValueError("Prometheus returned an invalid instant-vector result")
    return vector_result(payload)


async def query_matrix_range(
    client: httpx.AsyncClient,
    expression: str,
    *,
    start: int,
    end: int,
    step: int,
) -> dict[str, Any]:
    """Read a bounded matrix; only server-owned callers supply fixed PromQL."""
    if step <= 0 or end < start or (end - start) // step + 1 > 350:
        raise ValueError("Invalid bounded Prometheus range")
    response = await client.get(
        "/api/v1/query_range",
        params={
            "query": expression,
            "start": start,
            "end": end,
            "step": step,
        },
        headers={"Accept": "application/json"},
    )
    if 300 <= response.status_code < 400:
        raise httpx.HTTPStatusError(
            "Prometheus range query redirected",
            request=response.request,
            response=response,
        )
    response.raise_for_status()
    payload = response.json()
    if (
        not isinstance(payload, dict)
        or payload.get("status") != "success"
        or not isinstance(payload.get("data"), dict)
        or payload["data"].get("resultType") != "matrix"
        or not isinstance(payload["data"].get("result"), list)
    ):
        raise ValueError("Prometheus returned an invalid matrix result")
    return payload
