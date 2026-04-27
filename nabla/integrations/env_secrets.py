"""Resolve secrets from the process environment when vars are set, else from settings.

``get_settings()`` is cached; tests (and some deployments) change ``os.environ`` after
import. If a variable name is present in ``environ``, its value wins so empty string
means “unset” and matches runtime expectations.
"""

from __future__ import annotations

import os

from pydantic import SecretStr

from nabla.config_settings import get_settings


def secret_from_env_or_settings(
    env_name: str,
    *,
    settings_secret: SecretStr | None,
) -> str | None:
    """Return a non-empty secret, or ``None`` if missing or blank."""
    if env_name in os.environ:
        raw = os.environ[env_name].strip()
        return raw or None
    if settings_secret is None:
        return None
    raw = settings_secret.get_secret_value().strip()
    return raw or None


def google_cx_from_runtime(*, settings_cx: str | None) -> str | None:
    """Programmable Search id (cx) from env (any alias) or settings."""
    for env_name in ("GOOGLE_SEARCH_CX", "GOOGLE_CSE_ID", "GOOGLE_SEARCH_ENGINE_ID"):
        if env_name in os.environ:
            raw = os.environ[env_name].strip()
            return raw or None
    return (settings_cx or "").strip() or None


def google_search_credentials_runtime() -> tuple[str | None, str | None]:
    """``(api_key, cx)`` using env overrides when those names appear in ``environ``."""
    settings = get_settings()
    key = secret_from_env_or_settings(
        "GOOGLE_SEARCH_API_KEY",
        settings_secret=settings.google_search_api_key,
    )
    cx = google_cx_from_runtime(settings_cx=settings.google_search_cx)
    return key, cx
