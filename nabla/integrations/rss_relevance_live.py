"""Explicit operator-only RSS integration, plus one read-only MCP triage input.

The worker must run on TrueNAS. The CLI is read-only and has a separate opt-in.
``triage_inputs`` feeds ``GET /v2/rss/triage`` (TrueNAS only): the MCP client's
own model sorts the articles with the ``rss-triage`` skill; no scheduler or fallback.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import hashlib
import json
import logging
import os
import re
import time
from ipaddress import ip_address, ip_network
from typing import Any
from urllib.parse import urlsplit

import httpx
from redis.exceptions import RedisError

from nabla.integrations.freshrss_greader import recent_public_articles
from nabla.integrations.rss_relevance import filter_articles

_ALLOWED_PROMPT_HOSTS = {"langfuse.albandrieu.com", "langfuse"}
_MODEL = "fastapi-qwen"
logger = logging.getLogger(__name__)
_PRIVATE_NETS = tuple(ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def _private_host(hostname: str) -> bool:
    if hostname in {"litellm", "langfuse"}:
        return True
    try:
        address = ip_address(hostname)
    except ValueError:
        return False
    return address.version == 4 and any(address in network for network in _PRIVATE_NETS)


def _checked_litellm_url(value: str) -> str:
    """The configured homelab backend may move after the Freebox transition."""
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or not _private_host(parsed.hostname or "")
        or parsed.port != 4000
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise RSSConfigurationError("Dedicated private LiteLLM endpoint required")
    return value.rstrip("/")


_BAD_TAGS = {"production", "development", "service", "website", "internal", "active", "managed"}


class RSSConfigurationError(RuntimeError):
    """Safe failure type; never print credentials or upstream responses."""


def technology_projection(catalog: object) -> tuple[str, list[str]]:
    """Accept only the already-sanitized, revision-verified Backstage DTO."""
    from nabla.api.site_architecture_catalog import SiteArchitectureCatalogV2  # noqa: PLC0415 -- optional catalog dependency

    if not isinstance(catalog, SiteArchitectureCatalogV2):
        raise RSSConfigurationError("Verified Backstage catalog required")
    names: set[str] = set()
    for entity in catalog.entities:
        if entity.kind not in ("Component", "Resource", "System"):
            continue
        labels = [entity.metadata.name, *(entity.metadata.tags or [])]
        for value in labels:
            if value not in _BAD_TAGS and re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}", value):
                names.add(value)
    selected = sorted(names)[:250]
    if not selected:
        raise RSSConfigurationError("No safe technology labels in Backstage catalog")
    return catalog.catalogRevision, selected


def _checked_langfuse_host(value: str) -> None:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or (parsed.hostname not in _ALLOWED_PROMPT_HOSTS and not _private_host(parsed.hostname or ""))
        or parsed.port not in (None, 443, 3000)
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
        or (parsed.scheme == "http" and not _private_host(parsed.hostname or ""))
    ):
        raise RSSConfigurationError("Private Langfuse endpoint required")


async def managed_prompt(name: str, label: str) -> tuple[str, int]:
    """Fetch a versioned prompt; never use the general fallback-enabled helper."""
    from nabla.integrations.langfuse_prompts import _langfuse_client  # noqa: PLC0415 -- optional Langfuse SDK

    host = os.getenv("LANGFUSE_BASE_URL", "").strip()
    _checked_langfuse_host(host)
    if not os.getenv("LANGFUSE_PUBLIC_KEY") or not os.getenv("LANGFUSE_SECRET_KEY"):
        raise RSSConfigurationError("Langfuse credentials not configured")
    try:
        value = await asyncio.to_thread(
            lambda: _langfuse_client().get_prompt(name, type="text", label=label, max_retries=1),
        )
        prompt, version = value.compile(), value.version
        if not isinstance(prompt, str) or type(version) is not int or version <= 0:
            raise RSSConfigurationError("Unversioned Langfuse prompt rejected")
        return prompt, version
    except RSSConfigurationError:
        raise
    except Exception:
        raise RSSConfigurationError("Managed Langfuse prompt unavailable") from None


def _settings_litellm_url() -> str:
    from nabla.config_settings import get_settings  # noqa: PLC0415 -- homelab only

    return get_settings().litellm_url


async def lite_llm_json(client: httpx.AsyncClient, prompt: str, content: str, *, key: str) -> str:
    """One bounded TrueNAS LiteLLM chat completion with no tools or provider fallback."""
    if not key or "\r" in key or "\n" in key:
        raise RSSConfigurationError("Dedicated LiteLLM virtual key required")
    request = {
        "model": _MODEL,
        "temperature": 0,
        "max_tokens": 200,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": content},
        ],
    }
    try:
        async with asyncio.timeout(12):
            async with client.stream(
                "POST",
                _checked_litellm_url(_settings_litellm_url()) + "/v1/chat/completions",
                json=request,
                headers={"Authorization": "Bearer " + key, "Accept": "application/json"},
                follow_redirects=False,
            ) as response:
                if response.status_code != 200:
                    raise RSSConfigurationError("LiteLLM completion unavailable")
                body = bytearray()
                async for part in response.aiter_bytes():
                    if len(body) + len(part) > 8192:
                        raise RSSConfigurationError("LiteLLM response too large")
                    body.extend(part)
        message = json.loads(body)["choices"][0]["message"]["content"]
        if not isinstance(message, str) or len(message) > 4096:
            raise RSSConfigurationError("Invalid LiteLLM response")
        return message
    except (httpx.HTTPError, TimeoutError, ValueError, KeyError, IndexError, TypeError):
        raise RSSConfigurationError("LiteLLM response rejected") from None


@dataclass(slots=True)
class _RSSClassifier:
    """Version-bound, sanitized-only Redis cache; never an authorization source."""

    client: httpx.AsyncClient
    key: str
    redis_cache: Any
    revision: str
    technologies: list[str]
    prompt_version: int = 0

    async def resolve(self, name: str, label: str) -> tuple[str, int]:
        prompt, self.prompt_version = await managed_prompt(name, label)
        return prompt, self.prompt_version

    def verified_result(self, raw: str) -> bool:
        if not isinstance(raw, str) or len(raw) > 4096:
            return False
        try:
            value = json.loads(raw)
        except ValueError:
            return False
        return (
            isinstance(value, dict)
            and set(value) == {"relevant", "matched", "reason"}
            and type(value["relevant"]) is bool
            and isinstance(value["matched"], list)
            and len(value["matched"]) <= 250
            and all(isinstance(t, str) and t in self.technologies for t in value["matched"])
            and isinstance(value["reason"], str)
            and len(value["reason"]) <= 300
            and (not value["relevant"] or bool(value["matched"]))
        )

    async def classify(self, prompt: str, content: str) -> str:
        # Key ties the model and verified prompt/catalog versions to content.
        digest = hashlib.sha256(
            json.dumps(
                [
                    _MODEL,
                    self.revision,
                    self.prompt_version,
                    hashlib.sha256(prompt.encode()).hexdigest(),
                    content,
                ],
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode(),
        ).hexdigest()
        cache_key = "rss:v1:classify:" + digest
        if self.redis_cache is not None:
            try:
                async with asyncio.timeout(0.8):
                    cached = await self.redis_cache.get(cache_key)
                if self.verified_result(cached):
                    return cached
            except (RedisError, TimeoutError, OSError):
                # Avoid leaking Redis credentials, endpoint or key-derived metadata.
                logger.warning("RSS classification cache read unavailable; local inference required")
        result = await lite_llm_json(self.client, prompt, content, key=self.key)
        if self.verified_result(result) and self.redis_cache is not None:
            try:
                async with asyncio.timeout(0.8):
                    await self.redis_cache.set(cache_key, result, ex=86400)
            except (RedisError, TimeoutError, OSError):
                # The inference result remains usable even when Redis is down.
                logger.warning("RSS classification cache write unavailable; result not cached")
        return result


async def run_once() -> list[dict]:
    """Read-only execution in TrueNAS; no mark-read, no writes or notifications."""
    from nabla.api.external_probe_cache_redis import resolve_redis_client  # noqa: PLC0415 -- homelab only
    from nabla.api.runtime_environment import homelab_runtime_detected  # noqa: PLC0415 -- homelab only
    from nabla.api.site_architecture_catalog import fetch_site_catalog_v2  # noqa: PLC0415 -- homelab only
    from nabla.config_settings import get_settings  # noqa: PLC0415 -- homelab only

    if not homelab_runtime_detected():
        raise RSSConfigurationError("RSS inference is TrueNAS-only")
    settings = get_settings()
    _checked_litellm_url(settings.litellm_url)
    key = settings.litellm_api_key.get_secret_value()
    auth = os.getenv("FRESHRSS_RELEVANCE_AUTH", "").strip()
    if not auth:
        raise RSSConfigurationError("Dedicated FreshRSS account not configured")
    cf_id = os.getenv("FRESHRSS_CF_ACCESS_CLIENT_ID", "").strip()
    cf_secret = os.getenv("FRESHRSS_CF_ACCESS_CLIENT_SECRET", "").strip()
    catalog = await fetch_site_catalog_v2()
    revision, technologies = technology_projection(catalog)
    redis_cache = resolve_redis_client()
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(8),
        follow_redirects=False,
        trust_env=False,
    ) as client:

        async def fetch() -> list[dict]:
            return await recent_public_articles(
                client,
                auth=auth,
                cf_access_id=cf_id,
                cf_access_secret=cf_secret,
                limit=5,  # cap interactive LiteLLM cost and the 30-second overall deadline
                rotation=int(time.time() // 3600) % 20,
            )

        classifier = _RSSClassifier(
            client=client,
            key=key,
            redis_cache=redis_cache,
            revision=revision,
            technologies=technologies,
        )
        return await filter_articles(
            catalog_revision=revision,
            technologies=technologies,
            fetch_articles=fetch,
            load_prompt=classifier.resolve,
            classify_litellm=classifier.classify,
        )


async def triage_inputs() -> tuple[str, list[str], list[dict[str, str]]]:
    """Catalog technologies and the newest public FreshRSS articles; no LLM call (TrueNAS only)."""
    from nabla.api.runtime_environment import homelab_runtime_detected  # noqa: PLC0415 -- homelab only
    from nabla.api.site_architecture_catalog import fetch_site_catalog_v2  # noqa: PLC0415 -- homelab only

    if not homelab_runtime_detected():
        raise RSSConfigurationError("RSS triage is TrueNAS-only")
    auth = os.getenv("FRESHRSS_RELEVANCE_AUTH", "").strip()
    if not auth:
        raise RSSConfigurationError("Dedicated FreshRSS account not configured")
    revision, technologies = technology_projection(await fetch_site_catalog_v2())
    async with httpx.AsyncClient(timeout=httpx.Timeout(8), follow_redirects=False, trust_env=False) as client:
        articles = await recent_public_articles(
            client,
            auth=auth,
            cf_access_id=os.getenv("FRESHRSS_CF_ACCESS_CLIENT_ID", "").strip(),
            cf_access_secret=os.getenv("FRESHRSS_CF_ACCESS_CLIENT_SECRET", "").strip(),
        )
    return revision, technologies, articles


def main() -> int:
    parser = argparse.ArgumentParser(description="Private read-only RSS relevance pilot")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Offline configuration contract")
    group.add_argument("--once", action="store_true", help="One approved TrueNAS read-only run")
    group.add_argument("--publish", action="store_true", help="Classify once and publish opaque matches to Cloud")
    args = parser.parse_args()
    if args.check:
        print("CHECK: FreshRSS GReader + Backstage V2 + Langfuse + LiteLLM contract; no network")
        return 0
    if os.getenv("FRESHRSS_RELEVANCE_RUN_APPROVED") != "YES":
        raise RSSConfigurationError("Explicit read-only RSS run approval required")
    if args.publish and os.getenv("FRESHRSS_RELEVANCE_PUBLISH_APPROVED") != "YES":
        raise RSSConfigurationError("Explicit RSS publication approval required")
    rows = asyncio.run(run_once())
    if args.publish:
        from nabla.api.rss_publication import publish  # noqa: PLC0415 -- operator-only export

        if not rows:
            print(json.dumps({"state": "no_relevant_articles", "count": 0}))
            return 0
        result = asyncio.run(publish(rows))
        if result != "sent":
            raise RSSConfigurationError("RSS publication not accepted")
        print(json.dumps({"state": "published", "count": len(rows)}))
        return 0
    # Only approved, sanitized classification data; no raw feeds or secrets.
    print(json.dumps({"state": "classified", "count": len(rows), "matches": rows}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit("REJECTED: RSS relevance pilot could not be verified") from None
