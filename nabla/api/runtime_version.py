"""Non-blocking local-runtime comparison against FastAPI Cloud."""

from __future__ import annotations

import os
import re
from typing import Any

import httpx
from packaging.version import InvalidVersion, Version

_DEFAULT_CLOUD_LIVEZ = "https://fastapi-sample.fastapicloud.dev/livez"
_VERSION_RE = re.compile(r"(?P<version>\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)")
_VERSION_TIMEOUT_SEC = 2.5


def normalized_version(value: object) -> str | None:
    raw = str(value or "").strip()
    match = _VERSION_RE.search(raw)
    return match.group("version") if match else None


def version_is_behind(local: object, remote: object) -> bool | None:
    local_value = normalized_version(local)
    remote_value = normalized_version(remote)
    if local_value is None or remote_value is None:
        return None
    try:
        return Version(local_value) < Version(remote_value)
    except InvalidVersion:
        return None


async def fetch_cloud_version_status(local_version: object) -> dict[str, Any]:
    target = os.getenv("FASTAPI_CLOUD_LIVEZ_URL", _DEFAULT_CLOUD_LIVEZ).strip() or _DEFAULT_CLOUD_LIVEZ
    local = normalized_version(local_version) or str(local_version)
    try:
        timeout = httpx.Timeout(_VERSION_TIMEOUT_SEC)
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            response = await client.get(
                target,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, OSError, ValueError) as exc:
        return {
            "local_version": local,
            "cloud_version": None,
            "behind": None,
            "status_confirmed": False,
            "warning": "FastAPI Cloud version could not be confirmed",
            "error_kind": type(exc).__name__,
        }

    cloud_raw = payload.get("version") if isinstance(payload, dict) else None
    cloud = normalized_version(cloud_raw)
    behind = version_is_behind(local, cloud)
    return {
        "local_version": local,
        "cloud_version": cloud,
        "behind": behind,
        "status_confirmed": cloud is not None and behind is not None,
        "update_recommended": behind is True,
    }
