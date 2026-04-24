"""Public site context for Éléonore Andrieu (nickname Bababou).

The family-facing page is at :data:`PUBLIC_WEBSITE_URL`. Used by AI tools that
should load that content when the user clearly asks about her.

LangChain tool :func:`fetch_bababou_public_page` fetches that site when the model
delegates to it.
"""

from __future__ import annotations

import re
import urllib.request

from langchain_core.tools import tool

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


@tool
def fetch_bababou_public_page(user_question: str) -> str:
    """
    Load public content from bababou.com about Éléonore Andrieu (Bababou).

    Use when the user asks about Éléonore / Bababou, her story, or the family site.
    Pass the user's question verbatim in ``user_question`` so the tool can confirm
    the topic before fetching.
    """
    if not question_refers_to_eleonore(user_question):
        return (
            "Skipped fetching the site: the question does not appear to be about "
            "Éléonore (Bababou). Answer carefully or ask the user to clarify."
        )
    url = PUBLIC_WEBSITE_URL
    try:
        raw = _fetch_public_page_text(url)
    except OSError as exc:
        logger.warning("fetch_bababou_public_page: HTTP error: %s", exc)
        return f"Could not load {url}: {exc!s}"
    text = _html_to_visible_text(raw)
    if not text:
        return f"No readable text extracted from {url}."
    return f"Public page content from {url}:\n\n{text}"
