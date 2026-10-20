"""Signed Cloudflare Access JWT validation for read-only owner APIs."""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

import httpx
import jwt

from nabla.config_settings import get_settings

_ISSUER_PATTERN = re.compile(r"https://[a-z0-9-]+[.]cloudflareaccess[.]com")
_CACHE_TTL = 300
_lock = asyncio.Lock()
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


class OwnerConfigError(Exception):
    """No trusted Cloudflare Access application has been configured."""


class OwnerUnauthorized(Exception):
    """JWT invalid or human subject not authorized."""


class OwnerKeysUnavailable(Exception):
    """Key retrieval failed and no valid cache exists."""


def owner_settings() -> tuple[str, str, frozenset[str]]:
    cfg = get_settings()
    issuer = (getattr(cfg, "ops_access_issuer", None) or "").rstrip("/")
    audience = (getattr(cfg, "ops_access_aud", None) or "").strip()
    subjects = frozenset(v.strip() for v in (getattr(cfg, "ops_access_owner_subjects", None) or "").split(",") if v.strip())
    if not _ISSUER_PATTERN.fullmatch(issuer) or not audience or not subjects:
        raise OwnerConfigError
    return issuer, audience, subjects


async def signing_keys(issuer: str) -> list[dict[str, Any]]:
    cached = _cache.get(issuer)
    if cached is not None and time.monotonic() < cached[0]:
        return cached[1]
    async with _lock:
        cached = _cache.get(issuer)
        if cached is not None and time.monotonic() < cached[0]:
            return cached[1]
        try:
            async with httpx.AsyncClient(timeout=4, follow_redirects=False, trust_env=False) as client:
                response = await client.get(issuer + "/cdn-cgi/access/certs")
                response.raise_for_status()
                if len(response.content) > 131072:
                    raise ValueError("oversized JWKS")
                payload = response.json()
            keys = payload.get("keys") if isinstance(payload, dict) else None
            if not isinstance(keys, list) or not 1 <= len(keys) <= 12:
                raise ValueError("invalid JWKS")
            valid = [
                key
                for key in keys
                if isinstance(key, dict)
                and key.get("kty") == "RSA"
                and isinstance(key.get("kid"), str)
                and key["kid"]
                and key.get("use", "sig") == "sig"
                and key.get("alg", "RS256") == "RS256"
            ]
            if not valid:
                raise ValueError("missing RS256 keys")
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise OwnerKeysUnavailable from exc
        _cache[issuer] = (time.monotonic() + _CACHE_TTL, valid)
        return valid


async def verify_owner_token(token: str) -> str:
    """Return the allowed human subject; never accept unsigned headers."""
    issuer, audience, subjects = owner_settings()
    if not token or len(token) > 8192:
        raise OwnerUnauthorized
    try:
        header = jwt.get_unverified_header(token)
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise OwnerUnauthorized from exc
    if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str) or not header["kid"]:
        raise OwnerUnauthorized
    keys = await signing_keys(issuer)
    key = next((key for key in keys if key["kid"] == header["kid"]), None)
    if key is None:
        raise OwnerUnauthorized
    try:
        decoded = jwt.decode(
            token,
            jwt.PyJWK.from_dict(key, algorithm="RS256").key,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
            leeway=30,
            options={"require": ["iss", "aud", "iat", "nbf", "exp", "sub"]},
        )
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise OwnerUnauthorized from exc
    subject = decoded.get("sub")
    if decoded.get("type") != "app" or not isinstance(subject, str) or subject not in subjects or decoded.get("service_token_id") or decoded.get("common_name"):
        raise OwnerUnauthorized
    return subject


def assertion_from_headers(headers: Any) -> str:
    """Do not fall back to user-controlled email, cookies or URL parameters."""
    return headers.get("cf-access-jwt-assertion", "").strip()
