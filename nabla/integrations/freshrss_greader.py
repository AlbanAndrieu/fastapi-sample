"""Read-only, bounded FreshRSS GReader fetch for a dedicated service account.

A FreshRSS GoogleLogin token can also write. Deploy the service account with
only approved public subscriptions; this client never calls write endpoints.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpx

G_READER_ROOT = "https://freshrss.albandrieu.com/api/greader.php/reader/api/0/"
MAX_RESPONSE_BYTES = 1_500_000
MAX_ARTICLES = 20


class FreshRSSUnavailable(RuntimeError):
    """An opaque upstream/configuration failure without sensitive content."""


def _public_https_source(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 2048:
        return False
    try:
        url = urlsplit(value)
        host = (url.hostname or "").casefold().rstrip(".")
        if (
            url.scheme != "https"
            or not host
            or "." not in host
            or url.username
            or url.password
            or url.fragment
            or host.endswith((".local", ".lan", ".internal", ".int.albandrieu.com"))
            or url.port not in (None, 443)
        ):
            return False
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return True
    except ValueError:
        return False
    return False


class _RSSPlainText(HTMLParser):
    """Bounded HTML-to-text projection: untrusted RSS markup is never executable."""

    _IGNORED = frozenset({"script", "style", "template", "iframe", "svg"})
    _BREAKS = frozenset({"br", "p", "div", "li", "h1", "h2", "h3", "h4", "blockquote"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._IGNORED:
            self.ignored_depth += 1
        elif not self.ignored_depth and tag in self._BREAKS:
            self.parts.append(" ")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if not self.ignored_depth and tag in self._BREAKS:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._IGNORED and self.ignored_depth:
            self.ignored_depth -= 1
        elif not self.ignored_depth and tag in self._BREAKS:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self.ignored_depth:
            self.parts.append(data)


_BIDI_CONTROLS = re.compile("[\\u200b\\u200e\\u200f\\u202a-\\u202e\\u2066-\\u2069\\ufeff]")


def _plain_text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    # Bound CPU/memory before parsing, and decode escaped markup *before*
    # stripping active tags (e.g. &lt;script&gt;).
    parser = _RSSPlainText()
    parser.feed(unescape(value[: min(32768, max(4096, limit * 16))]))
    parser.close()
    cleaned = _BIDI_CONTROLS.sub("", "".join(parser.parts))
    cleaned = "".join(" " if ord(char) < 32 or ord(char) == 127 else char for char in cleaned)
    return re.sub(r"\\s+", " ", cleaned).strip()[:limit]


async def _read_document(client: httpx.AsyncClient, path: str, headers: dict[str, str]) -> dict:
    if path not in (
        "subscription/list?output=json",
        "stream/contents/reading-list?output=json&n=100",
    ):
        raise ValueError("GReader read operation not allowlisted")
    try:
        async with client.stream(
            "GET",
            G_READER_ROOT + path,
            headers=headers,
            follow_redirects=False,
        ) as response:
            if response.status_code != 200:
                raise FreshRSSUnavailable("GReader request refused")
            if response.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
                raise FreshRSSUnavailable("Unexpected GReader media type")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                    raise FreshRSSUnavailable("GReader document exceeds budget")
                body.extend(chunk)
        value = json.loads(body)
        if not isinstance(value, dict):
            raise FreshRSSUnavailable("Unexpected GReader schema")
        return value
    except (httpx.HTTPError, UnicodeError, ValueError, TimeoutError) as exc:
        if isinstance(exc, FreshRSSUnavailable):
            raise
        raise FreshRSSUnavailable("GReader unavailable") from None


def _approved_subscription_ids(subscriptions: object) -> set[str]:
    if not isinstance(subscriptions, list) or len(subscriptions) > 2000:
        raise FreshRSSUnavailable("Invalid subscription inventory")
    approved: set[str] = set()
    for entry in subscriptions:
        if isinstance(entry, dict) and isinstance(entry.get("id"), str) and 0 < len(entry["id"]) <= 512 and _public_https_source(entry.get("url")):
            approved.add(entry["id"])
    if not approved:
        raise FreshRSSUnavailable("No approved public subscriptions")
    return approved


def _safe_article(item: object, approved: set[str]) -> dict[str, str] | None:
    if not isinstance(item, dict):
        return None
    origin = item.get("origin")
    feed_id = origin.get("streamId") if isinstance(origin, dict) else None
    original_id = item.get("id")
    if feed_id not in approved or not isinstance(original_id, str) or not 1 <= len(original_id) <= 1024:
        return None
    title = _plain_text(item.get("title"), 300)
    if not title:
        return None
    excerpt = item.get("summary") or item.get("content") or {}
    summary = _plain_text(excerpt.get("content"), 2000) if isinstance(excerpt, dict) else ""
    opaque_id = hashlib.sha256((feed_id + "\x00" + original_id).encode("utf-8")).hexdigest()
    return {"id": opaque_id, "title": title, "summary": summary}


def _project_recent_public_articles(
    items: object,
    approved: set[str],
    limit: int,
) -> list[dict[str, str]]:
    if not isinstance(items, list) or len(items) > 1000:
        raise FreshRSSUnavailable("Invalid article inventory")
    articles: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items[:100]:
        projected = _safe_article(item, approved)
        if projected is None or projected["id"] in seen:
            continue
        seen.add(projected["id"])
        articles.append(projected)
        if len(articles) >= limit:
            break
    return articles


async def recent_public_articles(
    client: httpx.AsyncClient,
    *,
    auth: str,
    cf_access_id: str = "",
    cf_access_secret: str = "",
    limit: int = MAX_ARTICLES,
) -> list[dict[str, str]]:
    """Return sanitized metadata; no article URL, feed credentials or raw HTML."""
    if not auth.strip() or "\n" in auth or "\r" in auth:
        raise FreshRSSUnavailable("Dedicated GReader auth not configured")
    if bool(cf_access_id) != bool(cf_access_secret):
        raise FreshRSSUnavailable("Cloudflare service credential pair incomplete")
    if type(limit) is not int or not 1 <= limit <= MAX_ARTICLES:
        raise ValueError("Invalid article limit")
    headers = {
        "Authorization": "GoogleLogin auth=" + auth,
        "Accept": "application/json",
        "User-Agent": "nabla-fastapi-rss-relevance/1",
    }
    if cf_access_id:
        headers["CF-Access-Client-Id"] = cf_access_id
        headers["CF-Access-Client-Secret"] = cf_access_secret
    subscription_data = await _read_document(client, "subscription/list?output=json", headers)
    approved = _approved_subscription_ids(subscription_data.get("subscriptions"))
    articles_data = await _read_document(
        client,
        "stream/contents/reading-list?output=json&n=100",
        headers,
    )
    return _project_recent_public_articles(articles_data.get("items"), approved, limit)
