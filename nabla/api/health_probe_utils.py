"""Shared helpers for health and inverse-reachability probes."""

from __future__ import annotations

import ssl
from typing import Any

import httpx


def normalize_probe_error(message: str) -> str:
    """Collapse noisy upstream errors to short, user-facing diagnostics."""
    if "cloudflare tunnel error" in message.lower():
        return "Cloudflare Tunnel error"
    return message[:500]


def normalize_probe_result_errors(result: dict[str, Any]) -> dict[str, Any]:
    """Normalize the optional ``error`` field of one probe result."""
    err = result.get("error")
    if isinstance(err, str):
        return {**result, "error": normalize_probe_error(err)}
    return result


def looks_like_tls_error(message: str) -> bool:
    """Return whether a sanitized transport error is TLS/certificate related."""
    lower = message.lower()
    return any(
        marker in lower
        for marker in (
            "certificate",
            "cert verify",
            "hostname mismatch",
            "ssl",
            "tls",
            "unable to verify",
        )
    )


def is_textual_response(response: httpx.Response) -> bool:
    """Return whether a bounded response body is safe/useful for application checks."""
    content_type = response.headers.get("content-type", "").lower()
    return content_type.startswith("text/") or any(
        marker in content_type
        for marker in ("application/json", "application/problem+json", "application/xml")
    )


async def probe_https_tls_trusted(url: str) -> bool | None:
    """Return whether the default CA store trusts an HTTPS endpoint."""
    target = url.strip()
    if not target.lower().startswith("https:"):
        return None
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(5.0),
            verify=True,
            follow_redirects=True,
        ) as client:
            await client.get(target, headers={"User-Agent": "nabla-tls-verify/1.0"})
    except ssl.SSLError:
        return False
    except httpx.HTTPError as exc:
        if isinstance(exc.__cause__, ssl.SSLError):
            return False
        return None
    except OSError:
        return None
    return True
