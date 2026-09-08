"""Bounded Cloudflare edge probing for sickz exposure-policy reconciliation."""

from __future__ import annotations

from html import unescape
import os
import re
from typing import Any
from urllib.parse import urlsplit

import httpx

from nabla.api.provider_credentials import cloudflare_access_service_token_credentials

_MAX_EDGE_BODY_CHARS = 32_768
_DEFAULT_DENY_FRAGMENT = "this resource is blocked by this account's default-deny policy"
_ANONYMOUS_EDGE_HEADERS = {"User-Agent": "nabla-sickz-policy-probe/1.0"}
_CF_ACCESS_CLIENT_ID_HEADER = "CF-Access-Client-Id"
_CF_ACCESS_SERVICE_AUTH_HEADER = "CF-Access-Client-Secret"


def _hostname(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return (urlsplit(url).hostname or "").lower().rstrip(".") or None
    except ValueError:
        return None


def _response_contains_cloudflare_default_deny(response: httpx.Response) -> bool:
    """Detect Cloudflare account-level Default-Deny from a bounded HTML/text body."""
    content_type = response.headers.get("content-type", "").casefold()
    if content_type and not any(
        marker in content_type for marker in ("text/", "html", "xhtml")
    ):
        return False
    text = unescape(response.text[:_MAX_EDGE_BODY_CHARS])
    plain = re.sub(r"<[^>]+>", " ", text)
    normalized = re.sub(r"\s+", " ", plain).strip().casefold()
    normalized = normalized.replace(chr(0x2019), "'")
    return _DEFAULT_DENY_FRAGMENT in normalized


def _edge_response_evidence(response: httpx.Response) -> dict[str, Any]:
    """Return sanitized Cloudflare/Access evidence from one HTTP response."""
    server = response.headers.get("server", "").casefold()
    location = response.headers.get("location", "").casefold()
    cf_mitigated = response.headers.get("cf-mitigated", "").casefold()
    default_deny = _response_contains_cloudflare_default_deny(response)
    cloudflare_edge = bool(
        response.headers.get("cf-ray")
        or response.headers.get("cf-cache-status")
        or "cloudflare" in server
        or cf_mitigated
        or default_deny,
    )
    access_signal = bool(
        "cloudflareaccess.com" in location
        or "/cdn-cgi/access/" in location
        or cf_mitigated in {"challenge", "managed_challenge"},
    )
    return {
        "cloudflare_http_evidence": cloudflare_edge,
        "cloudflare_access_signal": access_signal,
        "cloudflare_default_deny": default_deny,
        "http_evidence_status": response.status_code,
    }


def _service_token_target_allowed(url: str) -> bool:
    """Never send the homelab Service Token outside the owned albandrieu.com zone."""
    host = _hostname(url)
    return bool(host and (host == "albandrieu.com" or host.endswith(".albandrieu.com")))


def _service_token_fallback_needed(evidence: dict[str, Any]) -> bool:
    """Retry only when the anonymous response explicitly looks Access-blocked."""
    return (
        evidence.get("cloudflare_default_deny") is True
        or evidence.get("cloudflare_access_signal") is True
    )


async def _probe_http_edge_evidence(
    url: str,
    *,
    allow_service_token: bool = True,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    """Probe anonymously first; retry with Cloudflare Service Auth on Access failure."""
    try:
        if urlsplit(url).port == 10443:
            return {
                "cloudflare_http_evidence": False,
                "cloudflare_access_signal": False,
                "http_probe_auth_mode": "anonymous",
                "http_evidence_skipped": True,
                "http_evidence_skip_reason": ("pfSense admin endpoint is not a Cloudflare edge target"),
                "cloudflare_service_auth_attempted": False,
            }
    except ValueError:
        pass

    token_status = cloudflare_access_service_token_credentials().as_dict()
    token_metadata: dict[str, Any] = {
        "cloudflare_service_token_configured": token_status["configured"],
        "cloudflare_service_token_configuration_stage": token_status["configuration_stage"],
        "cloudflare_service_auth_attempted": False,
    }
    if token_status["missing_variables"]:
        token_metadata["cloudflare_service_token_missing_variables"] = token_status["missing_variables"]
    if token_status["invalid_reference_variables"]:
        token_metadata["cloudflare_service_token_invalid_reference_variables"] = token_status["invalid_reference_variables"]

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(5.0),
            follow_redirects=False,
            transport=transport,
        ) as client:
            response = await client.get(url, headers=_ANONYMOUS_EDGE_HEADERS)
            anonymous_evidence = _edge_response_evidence(response)
            evidence = {
                **anonymous_evidence,
                "http_probe_auth_mode": "anonymous",
                "cloudflare_access_policy_missing_suspected": anonymous_evidence["cloudflare_default_deny"],
                **token_metadata,
            }

            if not allow_service_token or not _service_token_fallback_needed(evidence):
                return evidence
            if token_status["configured"] is not True:
                return evidence
            if not _service_token_target_allowed(url):
                evidence["cloudflare_access_fallback_skip_reason"] = "outside_trusted_zone"
                return evidence

            service_headers = {
                **_ANONYMOUS_EDGE_HEADERS,
                _CF_ACCESS_CLIENT_ID_HEADER: os.getenv(
                    "CF_ACCESS_CLIENT_ID",
                    "",
                ).strip(),
                _CF_ACCESS_SERVICE_AUTH_HEADER: os.getenv(
                    "CF_ACCESS_CLIENT_SECRET",
                    "",
                ).strip(),
            }
            evidence["cloudflare_service_auth_attempted"] = True
            try:
                service_response = await client.get(url, headers=service_headers)
            except (httpx.HTTPError, OSError) as exc:
                evidence["cloudflare_service_token_error_kind"] = type(exc).__name__
                return evidence

            service_evidence = _edge_response_evidence(service_response)
            access_passed = not (service_evidence["cloudflare_default_deny"] or service_evidence["cloudflare_access_signal"])
            evidence.update(
                {
                    "cloudflare_service_token_access_passed": access_passed,
                    "cloudflare_service_token_http_status": service_response.status_code,
                    "cloudflare_service_token_default_deny": service_evidence["cloudflare_default_deny"],
                    "cloudflare_service_token_access_signal": service_evidence["cloudflare_access_signal"],
                },
            )
            return evidence
    except (httpx.HTTPError, OSError):
        return {
            "cloudflare_http_evidence": False,
            "cloudflare_access_signal": False,
            "http_probe_auth_mode": "anonymous",
            **token_metadata,
        }
