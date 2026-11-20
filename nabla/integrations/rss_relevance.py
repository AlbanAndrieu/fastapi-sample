"""Offline-testable FreshRSS relevance pipeline; no external fallback or writeback."""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Awaitable, Callable, Sequence

PROMPT_NAME = "nabla-homelab-rss-relevance"
PROMPT_LABEL = "production"


async def filter_articles(
    *, catalog_revision: str, technologies: Sequence[str],
    fetch_articles: Callable[[], Awaitable[list[dict]]],
    load_prompt: Callable[[str, str], Awaitable[tuple[str, int]]],
    classify_litellm: Callable[[str, str], Awaitable[str]],
) -> list[dict]:
    """Only allowlisted, bounded metadata goes to the dedicated LiteLLM adapter.

    The adapter must enforce homelab-only URL/model and no fallback; this
    orchestration contract is deliberately not wired to production until then.
    """
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", catalog_revision):
        raise ValueError("invalid catalog revision")
    if not 1 <= len(technologies) <= 250 or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._+/#-]{0,79}", x) for x in technologies):
        raise ValueError("invalid technology projection")
    async with asyncio.timeout(30):
        prompt, version = await load_prompt(PROMPT_NAME, PROMPT_LABEL)
        if not prompt or len(prompt) > 8000 or type(version) is not int or version <= 0:
            raise ValueError("unverified managed prompt")
        articles = await fetch_articles()
        result = []
        seen: set[str] = set()
        for article in articles[:20]:
            identity = article.get("id")
            title = article.get("title")
            summary = article.get("summary", "")
            if not isinstance(identity, str) or not 1 <= len(identity) <= 250 or identity in seen:
                continue
            if not isinstance(title, str) or not isinstance(summary, str):
                continue
            seen.add(identity)
            content = json.dumps({
                "technologies": sorted(set(technologies)),
                "article": {"title": title[:300], "summary": summary[:2000]},
            }, ensure_ascii=False)
            raw = await classify_litellm(prompt, content)
            if not isinstance(raw, str) or len(raw) > 4096:
                raise ValueError("invalid classification")
            verdict = json.loads(raw)
            if not isinstance(verdict, dict) or set(verdict) != {"relevant", "matched", "reason"}:
                raise ValueError("invalid classification schema")
            matches = verdict["matched"]
            reason = verdict["reason"]
            if (type(verdict["relevant"]) is not bool or not isinstance(matches, list)
                    or not all(isinstance(x, str) and x in technologies for x in matches)
                    or not isinstance(reason, str) or len(reason) > 300
                    or (verdict["relevant"] and not matches)):
                raise ValueError("invalid classification values")
            if verdict["relevant"]:
                result.append({
                    "article_id": identity, "title": title[:300],
                    "matched": sorted(set(matches)), "reason": reason,
                    "catalogRevision": catalog_revision, "prompt_version": version,
                    "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
                })
        return result
