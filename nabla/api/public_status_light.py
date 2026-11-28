# ruff: noqa: PLW0603, S112 -- wave state is process-local; a failed probe task is dropped, never reported DOWN.
"""Budgeted PUBLIC HTTP reachability for FastAPI Cloud.

Never probe LAN, arbitrary or user-supplied targets. Access-protected public
routes are sampled only with the ``fastapi-sample-monitor`` Service Token
(CF_ACCESS_CLIENT_ID/SECRET) and only on albandrieu.com hosts. This is an
externally observed HTTP hint (Cloudflare edge, tunnel, origin), not TrueNAS
application health. No request may trigger the expensive private
health-board reconciliation.
"""

from __future__ import annotations

import asyncio
from ipaddress import ip_address
import os
import time
from urllib.parse import urlsplit

import httpx

from nabla.api.catalog_routes import routes_from_catalog
from nabla.api.dns_probe import probe_dns_hostname
from nabla.api.external_probe_cache_redis import resolve_redis_client
from nabla.api.provider_credentials import cloudflare_access_service_token_credentials
from nabla.api.sickz_cloudflare_edge import _service_token_target_allowed

# Nine HEAD requests maximum every three minutes per warm worker; three in
# flight. ~25 token-eligible routes are revisited within 9 min, before the
# 15 min expiry. Waves run only while a visitor keeps the replica awake.
MAX_WAVE = 9
INTERVAL_SECONDS = 180.0
MAX_AGE_SECONDS = 900.0
CONCURRENCY = 3
DEADLINE_SECONDS = 5.0
# Samples outlive scale-to-zero in Redis: a cold replica shows them at once as
# history (stale), on the same 12h30 horizon as the TrueNAS relay.
LAST_KNOWN_SECONDS = 45000
_REDIS_PREFIX = "nabla:public-light:v1:"

_revision = ""
_hydrated = ""
# Wall-clock observation times, so Redis can carry them across replicas.
_samples: dict[str, tuple[float, str]] = {}
_next_at = 0.0
_cursor = 0
_task: asyncio.Task[None] | None = None


def _approved_url(route: object, *, token: bool = False) -> str | None:
    """Allow only declared, public HTTPS :443 on owned domains.

    An Access-protected route is eligible only when the monitor token is
    configured, and only on the zone where that token may be sent.
    """
    if not getattr(route, "public", False):
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
    allowed = host in {"albanandrieu.com", "bababou.com", "fastapi-sample.fastapicloud.dev"} or host.endswith(".albandrieu.com") or host.endswith(".bababou.com")
    if not allowed or host.endswith(".int.albandrieu.com") or parsed.scheme != "https" or parsed.port not in (None, 443) or parsed.username or parsed.password or parsed.fragment:
        return None
    # Some honeypots and wildcard routes deliberately punish / requests.
    if host.startswith(("login.", "honeypot.")):
        return None
    if getattr(route, "access_required", True) and not (token and _service_token_target_allowed(url)):
        return None
    return url


def _targets(raw: dict) -> list[tuple[str, str, bool]]:
    """Primary route only; never distribute one result to multiple entity refs."""
    try:
        routes = routes_from_catalog(raw)
    except (KeyError, TypeError, ValueError):
        return []
    token = cloudflare_access_service_token_credentials().configured
    unique: dict[str, tuple[str, bool]] = {}
    ambiguous: set[str] = set()
    for route in routes:
        ref = route.entity_ref
        url = _approved_url(route, token=token)
        if url is None:
            continue
        # A multi-route entity is ambiguous, not one proven application.
        if ref in unique:
            ambiguous.add(ref)
        else:
            unique[ref] = (url, route.access_required)
    return sorted((ref, url, auth) for ref, (url, auth) in unique.items() if ref not in ambiguous)


async def _checked_status(client: httpx.AsyncClient, url: str, *, authenticated: bool = False) -> str:
    """One DNS-gated HTTP request; never treat an auth challenge as origin OK."""
    host = urlsplit(url).hostname
    if not host or (authenticated and not _service_token_target_allowed(url)):
        return "unknown"
    headers = {"User-Agent": "nabla-cloud-public-light/1", "Accept": "*/*"}
    if authenticated:
        # Access-protected route: fastapi-sample-monitor Service Token, never
        # forwarded since the client does not follow redirects.
        headers["CF-Access-Client-Id"] = os.getenv("CF_ACCESS_CLIENT_ID", "").strip()
        headers["CF-Access-Client-Secret"] = os.getenv("CF_ACCESS_CLIENT_SECRET", "").strip()
    try:
        dns = await asyncio.wait_for(probe_dns_hostname(host, timeout_seconds=0.9), timeout=1.1)
        addresses = dns.get("dns_resolved")
        if (
            dns.get("dns_state") != "ok"
            or not isinstance(addresses, list)
            or not addresses
            or len(addresses) > 4
            or any(not isinstance(address, str) or not ip_address(address).is_global for address in addresses)
        ):
            return "unknown"
        async with client.stream("HEAD", url, headers=headers) as response:
            status = response.status_code
        # A few well-behaved public origins do not implement HEAD.
        if status in (405, 501):
            async with client.stream("GET", url, headers={**headers, "Range": "bytes=0-0"}) as response:
                status = response.status_code
        if 200 <= status < 300:
            return "ok"
        if status in {401, 403, 407, 408, 429} or 300 <= status < 400:
            return "unknown"  # Access (token refused), redirect, throttling: no backend verdict.
        if 400 <= status < 600:
            return "fail"  # Observed public HTTP failure, NOT an internal service verdict.
    except (httpx.HTTPError, OSError, ValueError, TimeoutError):
        return "unknown"  # Observer failure does not prove an origin outage.
    return "unknown"


async def _run_wave(targets: list[tuple[str, str, bool]]) -> None:
    """Probe just one bounded wave; discard unfinished tasks, never mark them DOWN."""
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def one(ref: str, url: str, auth: bool, client: httpx.AsyncClient) -> tuple[str, str]:
        async with semaphore:
            return ref, await _checked_status(client, url, authenticated=auth)

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(2.0),
        follow_redirects=False,
        trust_env=False,
    ) as client:
        tasks = [asyncio.create_task(one(ref, url, auth, client)) for ref, url, auth in targets]
        try:
            done, pending = await asyncio.wait(tasks, timeout=DEADLINE_SECONDS)
            now = time.time()
            updates: dict[str, tuple[float, str]] = {}
            dropped: set[str] = set()
            for task in done:
                try:
                    ref, status = task.result()
                except (Exception, asyncio.CancelledError):
                    continue
                if status != "unknown":
                    _samples[ref] = updates[ref] = (now, status)
                else:
                    # A failed/blocked recheck must never leave an old green
                    # labelled current until its natural TTL expiry.
                    _samples.pop(ref, None)
                    dropped.add(ref)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            await _persist(updates, dropped)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()


async def _persist(updates: dict[str, tuple[float, str]], dropped: set[str]) -> None:
    """Best effort: a Redis failure loses history only, never a current verdict."""
    client = resolve_redis_client()
    if client is None or not _revision or not (updates or dropped):
        return
    key = _REDIS_PREFIX + _revision
    try:
        if updates:
            fields = {ref: f"{observed:.0f} {status}" for ref, (observed, status) in updates.items()}
            await asyncio.wait_for(client.hset(key, mapping=fields), timeout=0.5)
        if dropped:
            await asyncio.wait_for(client.hdel(key, *sorted(dropped)), timeout=0.5)
        await asyncio.wait_for(client.expire(key, LAST_KNOWN_SECONDS), timeout=0.5)
    except Exception:
        return


def _select_revision(revision: str) -> None:
    """A new catalogue revision never inherits samples of another one."""
    global _revision, _next_at, _cursor
    if _revision != revision:
        _revision = revision
        _samples.clear()
        _cursor = 0
        _next_at = 0.0


async def hydrate(revision: str) -> None:
    """Once per revision, reload the last samples a previous replica stored."""
    global _hydrated
    if _hydrated == revision:
        return
    _select_revision(revision)
    client = resolve_redis_client()
    if client is None:
        _hydrated = revision
        return
    try:
        stored = await asyncio.wait_for(client.hgetall(_REDIS_PREFIX + revision), timeout=0.15)
    except Exception:
        return  # Retried on the next request; the page never waits longer.
    _hydrated = revision
    now = time.time()
    for field, value in (stored or {}).items():
        ref = field.decode() if isinstance(field, bytes) else str(field)
        observed_text, _, status = (value.decode() if isinstance(value, bytes) else str(value)).partition(" ")
        try:
            observed = float(observed_text)
        except ValueError:
            continue
        if status not in ("ok", "fail") or not 0 <= now - observed < LAST_KNOWN_SECONDS:
            continue
        if ref not in _samples or _samples[ref][0] < observed:
            _samples[ref] = (observed, status)


def start_light_public_checks(revision: str, raw: dict) -> None:
    """Non-blocking, single-flight Cloud trigger, never from a private probe."""
    global _next_at, _cursor, _task
    if not isinstance(raw, dict) or raw.get("catalogRevision") != revision:
        return
    now = time.monotonic()
    _select_revision(revision)
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
    now = time.time()
    return {ref: status for ref, (observed, status) in _samples.items() if 0 <= now - observed < MAX_AGE_SECONDS}


def last_known_public_states(revision: str) -> dict[str, str]:
    """Observed status too old to be current: history for a cold first page."""
    if revision != _revision:
        return {}
    now = time.time()
    return {ref: status for ref, (observed, status) in _samples.items() if MAX_AGE_SECONDS <= now - observed < LAST_KNOWN_SECONDS}


def reset_light_public_checks() -> None:
    """Isolated test seam; do not reuse prior samples or run a background poller."""
    global _revision, _hydrated, _next_at, _cursor, _task
    if _task is not None and not _task.done():
        _task.cancel()
    _revision = ""
    _hydrated = ""
    _samples.clear()
    _next_at = 0.0
    _cursor = 0
    _task = None
