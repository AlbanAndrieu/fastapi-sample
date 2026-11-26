"""Budgeted, unauthenticated PUBLIC HTTP reachability for FastAPI Cloud.

Never probe LAN, Access-protected, arbitrary or user-supplied targets. This is
an externally observed HTTP availability hint, not TrueNAS application health.
No request may trigger the expensive private health-board reconciliation.
"""

from __future__ import annotations

import asyncio
from ipaddress import ip_address
import time
from urllib.parse import urlsplit

import httpx

from nabla.api.catalog_routes import routes_from_catalog
from nabla.api.dns_probe import probe_dns_hostname

# Six HEAD requests maximum every three minutes per warm worker; two in flight.
MAX_WAVE = 6
INTERVAL_SECONDS = 180.0
MAX_AGE_SECONDS = 900.0
CONCURRENCY = 2
DEADLINE_SECONDS = 5.0

_revision = ""
_samples: dict[str, tuple[float, str]] = {}
_next_at = 0.0
_cursor = 0
_task: asyncio.Task[None] | None = None


def _approved_url(route: object) -> str | None:
    """Allow only declared, public, unprotected HTTPS :443 on owned domains."""
    if not getattr(route, "public", False) or getattr(route, "access_required", True):
        return None
    if getattr(route, "lifecycle", None) in {"planned", "disabled"}:
        return None
    if getattr(route, "protocol", "") != "HTTPS" or getattr(route, "port", None) not in (None, 443):
        return None
    url = getattr(route, "public_https_probe_url", None)
    if not isinstance(url, str):
        return None
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    allowed = (
        host in {"albanandrieu.com", "bababou.com", "fastapi-sample.fastapicloud.dev"}
        or host.endswith(".albandrieu.com")
        or host.endswith(".bababou.com")
    )
    if (
        not allowed or host.endswith(".int.albandrieu.com")
        or parsed.scheme != "https" or parsed.port not in (None, 443)
        or parsed.username or parsed.password or parsed.fragment
    ):
        return None
    # Some honeypots and wildcard routes deliberately punish / requests.
    if host.startswith(("login.", "honeypot.")):
        return None
    return url


def _targets(raw: dict) -> list[tuple[str, str]]:
    """Primary route only; never distribute one result to multiple entity refs."""
    try:
        routes = routes_from_catalog(raw)
    except (KeyError, TypeError, ValueError):
        return []
    unique: dict[str, str] = {}
    ambiguous: set[str] = set()
    for route in routes:
        ref = route.entity_ref
        url = _approved_url(route)
        if url is None:
            continue
        # A multi-route entity is ambiguous, not one proven application.
        if ref in unique:
            ambiguous.add(ref)
        else:
            unique[ref] = url
    return sorted((ref, url) for ref, url in unique.items() if ref not in ambiguous)


async def _checked_status(client: httpx.AsyncClient, url: str) -> str:
    """One DNS-gated HTTP request; never treat an auth challenge as origin OK."""
    host = urlsplit(url).hostname
    if not host:
        return "unknown"
    try:
        dns = await asyncio.wait_for(probe_dns_hostname(host, timeout_seconds=0.9), timeout=1.1)
        addresses = dns.get("dns_resolved")
        if (
            dns.get("dns_state") != "ok" or not isinstance(addresses, list)
            or not addresses or len(addresses) > 4
            or any(not isinstance(address, str) or not ip_address(address).is_global for address in addresses)
        ):
            return "unknown"
        async with client.stream(
            "HEAD", url, headers={"User-Agent": "nabla-cloud-public-light/1", "Accept": "*/*"},
        ) as response:
            status = response.status_code
        # A few well-behaved public origins do not implement HEAD.
        if status in (405, 501):
            async with client.stream(
                "GET", url, headers={"User-Agent": "nabla-cloud-public-light/1", "Range": "bytes=0-0"},
            ) as response:
                status = response.status_code
        if 200 <= status < 300:
            return "ok"
        if status in {401, 403, 407, 408, 429} or 300 <= status < 400:
            return "unknown"  # Access, redirect and throttling do not prove backend health.
        if 400 <= status < 600:
            return "fail"  # Observed public HTTP failure, NOT an internal service verdict.
    except (httpx.HTTPError, OSError, ValueError, TimeoutError):
        return "unknown"  # Observer failure does not prove an origin outage.
    return "unknown"


async def _run_wave(targets: list[tuple[str, str]]) -> None:
    """Probe just one bounded wave; discard unfinished tasks, never mark them DOWN."""
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def one(ref: str, url: str, client: httpx.AsyncClient) -> tuple[str, str]:
        async with semaphore:
            return ref, await _checked_status(client, url)

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(2.0), follow_redirects=False, trust_env=False,
    ) as client:
        tasks = [asyncio.create_task(one(ref, url, client)) for ref, url in targets]
        try:
            done, pending = await asyncio.wait(tasks, timeout=DEADLINE_SECONDS)
            now = time.monotonic()
            for task in done:
                try:
                    ref, status = task.result()
                except (Exception, asyncio.CancelledError):
                    continue
                if status != "unknown":
                    _samples[ref] = (now, status)
                else:
                    # A failed/blocked recheck must never leave an old green
                    # labelled current until its natural TTL expiry.
                    _samples.pop(ref, None)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()


def start_light_public_checks(revision: str, raw: dict) -> None:
    """Non-blocking, single-flight Cloud trigger, never from a private probe."""
    global _revision, _next_at, _cursor, _task
    if not isinstance(raw, dict) or raw.get("catalogRevision") != revision:
        return
    now = time.monotonic()
    if _revision != revision:
        _revision = revision
        _samples.clear()
        _cursor = 0
        _next_at = 0.0
    if (_task is not None and not _task.done()) or now < _next_at:
        return
    targets = _targets(raw)
    if not targets:
        _next_at = now + INTERVAL_SECONDS
        return
    wave = [targets[(i + _cursor) % len(targets)] for i in range(min(MAX_WAVE, len(targets)))]
    _cursor = (_cursor + len(wave)) % len(targets)
    _next_at = now + INTERVAL_SECONDS
    _task = asyncio.create_task(_run_wave(wave), name="cloud-public-light-head")


def fresh_public_states(revision: str) -> dict[str, str]:
    """Only return actually observed status, expiring each probe independently."""
    if revision != _revision:
        return {}
    now = time.monotonic()
    return {
        ref: status
        for ref, (observed, status) in _samples.items()
        if 0 <= now - observed < MAX_AGE_SECONDS
    }


def reset_light_public_checks() -> None:
    """Isolated test seam; do not reuse prior samples or run a background poller."""
    global _revision, _next_at, _cursor, _task
    if _task is not None and not _task.done():
        _task.cancel()
    _revision = ""
    _samples.clear()
    _next_at = 0.0
    _cursor = 0
    _task = None
