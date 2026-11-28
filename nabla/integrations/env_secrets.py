"""Resolve secrets from the process environment when vars are set, else from settings.

``get_settings()`` is cached; tests (and some deployments) change ``os.environ`` after
import. If a variable name is present in ``environ``, its value wins so empty string
means “unset” and matches runtime expectations.
"""

from __future__ import annotations

import os

from pydantic import SecretStr


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
