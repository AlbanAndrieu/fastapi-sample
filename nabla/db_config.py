"""PostgreSQL URL construction from POSTGRES_* environment variables."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.engine.url import URL

# Direct Supabase DB hostnames resolve to IPv6-only by default; IPv4-only networks need
# Supavisor session pooler (see SUPABASE_POOLER_REGION in settings).
_SUPABASE_DIRECT_DB_HOST = re.compile(r"^db\.(?P<ref>[^.]+)\.supabase\.co$", re.IGNORECASE)


def normalize_postgres_driver(driver: str, *, sqlalchemy_psycopg: bool = False) -> str:
    """Normalize driver name for libpq URIs or SQLAlchemy."""
    base = driver.lower().replace("+asyncpg", "").replace("+psycopg", "")
    if not base:
        base = "postgresql"
    if sqlalchemy_psycopg and base == "postgresql":
        return "postgresql+psycopg"
    return base


def is_supabase_postgres_host(host: str) -> bool:
    """True if host is a Supabase database endpoint (direct or shared pooler)."""
    h = host.strip().lower()
    return h.endswith(".supabase.co") or "pooler.supabase.com" in h


def is_supabase_supavisor_pooler_host(host: str) -> bool:
    """Shared Supavisor hostname (session or transaction pooler), not direct db.*."""
    return "pooler.supabase.com" in host.strip().lower()


def extract_project_ref_from_db_host(host: str) -> str | None:
    """Return project ref from ``db.<ref>.supabase.co`` or None."""
    match = _SUPABASE_DIRECT_DB_HOST.match(host.strip())
    return match.group("ref") if match else None


def extract_supabase_project_ref_from_url(url: str | None) -> str | None:
    """Parse project ref from ``https://<ref>.supabase.co`` (or with ``db.<ref>`` hostname)."""
    raw = (url or "").strip()
    if not raw:
        return None
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    hostname = (parsed.hostname or "").strip().lower()
    if not hostname.endswith(".supabase.co"):
        return None
    stem = hostname.removesuffix(".supabase.co")
    if stem.startswith("db."):
        stem = stem[3:]
    parts = [p for p in stem.split(".") if p]
    return parts[-1] if parts else None


def resolve_supabase_project_ref(
    *,
    explicit: str | None,
    supabase_url: str | None,
    db_style_host: str,
) -> str | None:
    """Prefer explicit ref, then dashboard URL, then ``db.<ref>.supabase.co`` host."""
    if explicit and (stripped := explicit.strip()):
        return stripped
    from_url = extract_supabase_project_ref_from_url(supabase_url)
    if from_url:
        return from_url
    return extract_project_ref_from_db_host(db_style_host)


def ensure_supavisor_pooler_username(host: str, user: str, project_ref: str | None) -> str:
    """Ensure Supavisor pooler usernames include tenant suffix ``<role>.<project_ref>``."""
    if not is_supabase_supavisor_pooler_host(host):
        return user
    u = user.strip()
    if not u:
        return user
    if "." in u:
        return u
    ref = (project_ref or "").strip()
    if ref:
        return f"{u}.{ref}"
    return user


def merge_postgres_query_sslmode_require(query: str | None) -> str | None:
    """Append sslmode=require when no ssl/sslmode is set (needed for Supabase)."""
    params = query_string_to_dict(query)
    lower_keys = {k.lower() for k in params}
    if "sslmode" not in lower_keys and "ssl" not in lower_keys:
        params["sslmode"] = "require"
    if not params:
        return None
    return "&".join(f"{k}={v}" for k, v in sorted(params.items()))


def supabase_session_pooler_targets(
    host: str,
    user: str,
    port: int,
    *,
    pooler_region: str | None,
) -> tuple[str, str, int, bool]:
    """If using direct db.<ref>.supabase.co and region is set, use IPv4-capable session pooler.

    Returns:
        (host, user, port, did_rewrite)
    """
    region = (pooler_region or "").strip()
    if not region:
        return host, user, port, False
    stripped_host = host.strip()
    match = _SUPABASE_DIRECT_DB_HOST.match(stripped_host)
    if not match:
        return host, user, port, False
    ref = match.group("ref")
    pooler_host = f"aws-0-{region}.pooler.supabase.com"
    pooler_port = 5432
    u = user.strip()
    pooler_user = f"postgres.{ref}" if u.lower() == "postgres" else u
    return pooler_host, pooler_user, pooler_port, True


def query_string_to_dict(query: str | None) -> dict[str, Any]:
    """Parse optional query fragment (e.g. ``pgbouncer=true``) for SQLAlchemy URL."""
    if query is None or not query.strip():
        return {}
    q = query.strip().lstrip("?")
    out: dict[str, Any] = {}
    for part in q.split("&"):
        if not part or "=" not in part:
            continue
        key, _, value = part.partition("=")
        key, value = key.strip(), value.strip()
        if not key:
            continue
        out[key] = value
    return out


def _is_truthy(value: str | None) -> bool:
    """Return True for common truthy string values."""
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_sqlalchemy_psycopg_connect_args(query: str | None) -> dict[str, Any]:
    """Build SQLAlchemy connect args for psycopg URLs.

    pgbouncer transaction pooling invalidates server-side prepared statements across
    backend hops. Disabling auto-prepare avoids ``DuplicatePreparedStatement`` and
    ``InvalidSqlStatementName`` failures.
    """
    params = query_string_to_dict(query)
    if _is_truthy(params.get("pgbouncer")):
        return {"prepare_threshold": None}
    return {}


def make_postgres_url(
    *,
    driver: str,
    username: str,
    password: str,
    host: str,
    port: int,
    database: str,
    query: str | None,
    sqlalchemy_psycopg: bool,
) -> URL:
    """Build a SQLAlchemy URL from discrete Postgres components."""
    return URL.create(
        drivername=normalize_postgres_driver(driver, sqlalchemy_psycopg=sqlalchemy_psycopg),
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
        query=query_string_to_dict(query),
    )
