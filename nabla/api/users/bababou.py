"""Public site context for Éléonore Andrieu (nickname Bababou).

The family-facing page is at :data:`PUBLIC_WEBSITE_URL`. Used by AI tools that
should load that content when the user clearly asks about her.

LangChain tool :func:`fetch_bababou_public_page` fetches that site when the model
delegates to it.
"""

from __future__ import annotations

import re
import urllib.request
from urllib.parse import urljoin, urlparse

from langchain_core.tools import tool

from nabla.integrations.web_search_factory import (
    resolve_web_search_provider,
    web_search_to_context_string,
)
from nabla.utils.logger import logger

PUBLIC_WEBSITE_URL = "https://www.bababou.com/"

DISPLAY_NAME = "Éléonore Célèste Andrieu Brooke"
NICKNAME = "Bababou"

WEBSITE_QUERY_MARKERS: tuple[str, ...] = (
    "éléonore",
    "eleonore",
    "éléonore andrieu",
    "eleonore andrieu",
    "bababou",
    "bababou célèste andrieu brooke",
    "bababou célèste andrieu",
    "bababou célèste",
    "bababou andrieu",
    "bababou",
    "bababou.com",
    "child of alban andrieu",
    "child of alban andrieu and rachael brooke",
    "baby",
    "daugher"
)


def question_refers_to_eleonore(question: str) -> bool:
    """Return True if ``question`` likely asks about Éléonore (Bababou), not generic Andrieu-only queries."""
    q = question.casefold()
    return any(marker.casefold() in q for marker in WEBSITE_QUERY_MARKERS)


def _html_to_visible_text(html: str, *, max_chars: int = 14_000) -> str:
    """Strip scripts/styles/tags so the model gets readable plain text."""
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def _fetch_public_page_text(url: str) -> str:
    req = urllib.request.Request(  # noqa: S310 — HTTPS fixed URL from callers only
        url,
        headers={"User-Agent": f"nabla-ai-workflow/1.0 (+{url})"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310
        return resp.read().decode(
            resp.headers.get_content_charset() or "utf-8",
            errors="replace",
        )


def _same_host(url: str, *, origin_netloc: str) -> bool:
    try:
        return urlparse(url).netloc == origin_netloc
    except ValueError:
        return False


def _sitemap_locs(xml_body: str) -> list[str]:
    return [
        m.strip()
        for m in re.findall(r"<loc>\s*([^<]+?)\s*</loc>", xml_body, flags=re.IGNORECASE | re.DOTALL)
        if m.strip()
    ]


def _http_sitemap_fallback(*, max_pages: int = 5, total_budget: int = 24_000) -> str:
    origin = PUBLIC_WEBSITE_URL.rstrip("/")
    origin_netloc = urlparse(origin).netloc
    sitemap_url = urljoin(origin + "/", "sitemap.xml")
    urls: list[str] = [PUBLIC_WEBSITE_URL]
    try:
        xml_body = _fetch_public_page_text(sitemap_url)
    except OSError:
        xml_body = ""
    for loc in _sitemap_locs(xml_body):
        if _same_host(loc, origin_netloc=origin_netloc) and not loc.lower().endswith(".xml"):
            urls.append(loc)
        if len(urls) >= max_pages:
            break
    chunks: list[str] = []
    used = 0
    for url in urls[:max_pages]:
        try:
            raw = _fetch_public_page_text(url)
        except OSError as exc:
            chunks.append(f"URL: {url}\n(fetch failed: {exc!s})\n")
            continue
        room = max(0, total_budget - used)
        if room <= 0:
            break
        text = _html_to_visible_text(raw, max_chars=min(6000, room))
        used += len(text)
        if text:
            chunks.append(f"URL: {url}\n\n{text}\n")
    body = "\n---\n".join(chunks).strip()
    return body or f"Could not extract readable text from {PUBLIC_WEBSITE_URL}."


@tool
def fetch_bababou_public_page(user_question: str | None = None) -> str:
    """
    Load public content from bababou.com about Éléonore Célèste Andrieu Brooke (Bababou).

    Use when the user asks about Éléonore Célèste Andrieu Brooke / Bababou, her story, or the family site.
    Pass the user's question verbatim in ``user_question`` so the tool can confirm
    the topic before fetching.
    """
    if not user_question or not user_question.strip():
        return (
            "Missing `user_question`. Pass the user's question verbatim so I can confirm "
            "they are asking about Éléonore Célèste Andrieu Brooke (Bababou) before fetching site context."
        )
    if not question_refers_to_eleonore(user_question):
        return (
            "Skipped fetching the site: the question does not appear to be about "
            "Éléonore (Bababou). Answer carefully or ask the user to clarify."
        )

    if resolve_web_search_provider() is not None:
        q = f"{user_question} site:bababou.com"
        try:
            ctx = web_search_to_context_string(q).strip()
        except Exception as exc:
            logger.warning("fetch_bababou_public_page: web search failed: %s", exc)
            ctx = ""
        if ctx:
            return f"Public site context (web search; {PUBLIC_WEBSITE_URL}):\n\n{ctx}"

    return (
        "Public site context (direct HTTP + sitemap; no web search API configured or no results):\n\n"
        f"{_http_sitemap_fallback()}"
    )
