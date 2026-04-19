"""Lazy Appwrite server SDK client helpers."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from nabla.config_settings import get_settings

try:  # pragma: no cover - optional dependency in local/dev environments
    from appwrite.client import Client
    from appwrite.services.health import Health
except ImportError:  # pragma: no cover - handled by runtime checks
    Client = None
    Health = None


def _appwrite_config() -> tuple[str, str, str] | None:
    """Return normalized Appwrite endpoint/project/key when fully configured."""
    settings = get_settings()
    endpoint = (settings.appwrite_endpoint or "").strip()
    project_id = (settings.appwrite_project_id or "").strip()
    if settings.appwrite_api_key is None:
        return None
    api_key = settings.appwrite_api_key.get_secret_value().strip()
    if not endpoint or not project_id or not api_key:
        return None
    return endpoint, project_id, api_key


@lru_cache(maxsize=1)
def get_appwrite_client() -> Any | None:
    """Return an Appwrite ``Client`` when SDK and credentials are available."""
    config = _appwrite_config()
    if config is None or Client is None:
        return None
    endpoint, project_id, api_key = config
    return Client().set_endpoint(endpoint).set_project(project_id).set_key(api_key)


def appwrite_health() -> dict[str, Any]:
    """Fetch Appwrite health summary via server SDK."""
    if Health is None:
        msg = "Appwrite SDK is not installed; add dependency `appwrite`."
        raise RuntimeError(msg)
    client = get_appwrite_client()
    if client is None:
        msg = "APPWRITE_ENDPOINT, APPWRITE_PROJECT_ID, and APPWRITE_API_KEY must be configured."
        raise RuntimeError(msg)
    return Health(client).get()
