"""Lazy Supabase Python client for REST/Auth/Storage (Postgres remains via POSTGRES_*)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from supabase import create_client

from nabla.config_settings import get_settings


@lru_cache(maxsize=1)
def get_supabase_client() -> Any | None:
    """Return a ``supabase.Client`` when ``SUPABASE_URL`` and ``SUPABASE_SERVICE_ROLE_KEY`` are set.

    The service role key is the JWT from Supabase Dashboard → Settings → API. It is not the same as
    a Supabase CLI access token (``sbp_...``).
    """
    settings = get_settings()
    if not settings.supabase_url or settings.supabase_service_role_key is None:
        return None

    return create_client(
        settings.supabase_url,
        settings.supabase_service_role_key.get_secret_value(),
    )
