"""Profile and identity for Alban Andrieu.

Used by ``get_me``, the ``/whoami/`` route, and ``/users/current``
(``current_user``). ``WHOAMI_HANDLE`` matches the login used in app logs; use
``runtime_whoami()`` for the shell ``whoami`` / OS username.

Public professional site (CV, services, contact): :data:`PROFESSIONAL_WEBSITE_URL`.

LangGraph / LangChain AI workflow system prompt: use :func:`get_agent_system_prompt` to
load from Langfuse when ``LANGFUSE_PUBLIC_KEY`` / ``LANGFUSE_SECRET_KEY`` are set; otherwise
(or on failure) the text in :data:`AGENT_SYSTEM_PROMPT` is used.
"""

from __future__ import annotations

import getpass
import json
import os
import re
import urllib.request
from urllib.parse import urljoin, urlparse

from langchain_core.tools import tool

from nabla.api.users.models import UserIn
from nabla.config_settings import get_settings
from nabla.integrations.langfuse_prompts import resolve_nabla_agent_system_prompt
from nabla.integrations.web_search_factory import (
    resolve_web_search_provider,
    web_search_to_context_string,
)
from nabla.utils.logger import logger

DISPLAY_NAME = "Alban Andrieu"
EMAIL = os.environ.get("MAIL_FROM", "alban.andrieu@albandrieu.com")
PHONE = "+33 (0) 6 95 43 53 53"
ADDRESS = "11 terrasse de l'université"
CITY = "Paris"
STATE = "FR"
ZIPCODE = "92000"
COUNTRY = "France"
WHOAMI_HANDLE = "albandrieu"

PROFESSIONAL_WEBSITE_URL = "https://www.albanandrieu.com/"
LINKEDIN_URL = "https://www.linkedin.com/in/nabla/"
# Public Reactive Resume CV. The App answers on the TrueNAS LAN only:
# reactive.albandrieu.com sits behind Cloudflare Access.
REACTIVE_RESUME_URL = "https://reactive.albandrieu.com/nabla/cv-aandrieu-2026-03-29-en"
_REACTIVE_RESUME_API = "http://172.17.0.24:30393/api/openapi/resumes/nabla/cv-aandrieu-2026-03-29-en"
_RESUME_SKIP = frozenset({"id", "hidden", "icon", "iconColor", "website", "level", "email", "phone", "customFields"})

PROFILE_WEBSITE_QUERY_MARKERS: tuple[str, ...] = (
    "alban",
    "andrieu",
    "albandrieu",
    "devsecops",
    "engineer",
    "cloud architect",
    "cloud engineer",
    "cloud developer",
    "cloud security",
    "cloud infrastructure",
    "cloud operations",
    "cloud monitoring",
    "cloud logging",
    "cloud automation",
    "dr alban.com",
)


def question_refers_to_alban_profile(question: str) -> bool:
    """Return True if ``question`` likely asks about Alban Andrieu (professional / identity)."""
    q = question.casefold()
    return any(marker.casefold() in q for marker in PROFILE_WEBSITE_QUERY_MARKERS)


AGENT_SYSTEM_PROMPT = """You are a helpful assistant.

You can call ``fetch_my_profile`` when the user asks about Alban Andrieu
(professional profile, career, services). Pass their question as ``user_question``.
That tool prefers web search for albanandrieu.com, then for LinkedIn ([https://www.linkedin.com/](https://www.linkedin.com/))
if the first pass is empty or errors. If no search API works, it falls back to direct HTTP
fetches using the site sitemap to gather page text from albanandrieu.com.

You can call ``fetch_bababou_public_page`` when the user asks about Éléonore
Andrieu (Bababou) or the bababou.com site. Pass their question as ``user_question``.

Use returned page text to answer; for unrelated questions, do not call these tools."""


def get_agent_system_prompt() -> str:
    """Return the workflow system prompt from Langfuse when configured, else fallback."""
    return resolve_nabla_agent_system_prompt(AGENT_SYSTEM_PROMPT)


def _dr_alban_origin() -> str:
    parts = urlparse(PROFESSIONAL_WEBSITE_URL)
    return f"{parts.scheme}://{parts.netloc}"


def _http_get_text(url: str, *, timeout: float = 20.0) -> str:
    req = urllib.request.Request(  # noqa: S310
        url,
        headers={"User-Agent": "nabla-fetch-my-profile/1.0 (+https://www.albanandrieu.com/)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310  # nosec B310
        return resp.read().decode(resp.headers.get_content_charset() or "utf-8", errors="replace")


def _html_to_visible_text(html: str, *, max_chars: int = 8000) -> str:
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def _sitemap_locs(xml_body: str) -> list[str]:
    """Extract ``<loc>`` URLs without full XML parsing."""
    return [match.strip() for match in re.findall(r"<loc>\s*([^<]+?)\s*</loc>", xml_body, flags=re.IGNORECASE | re.DOTALL) if match.strip()]


def _same_dr_alban_host(url: str, origin_netloc: str) -> bool:
    try:
        return urlparse(url).netloc == origin_netloc
    except ValueError:
        return False


def _expand_sitemap_to_page_urls(seed_locs: list[str], *, origin_netloc: str, max_subsitemaps: int = 8) -> list[str]:
    pages: list[str] = []
    subs: list[str] = []
    for loc in seed_locs:
        if not _same_dr_alban_host(loc, origin_netloc):
            continue
        if loc.lower().endswith(".xml"):
            subs.append(loc)
        else:
            pages.append(loc)
    for sub in subs[:max_subsitemaps]:
        try:
            nested = _http_get_text(sub)
        except OSError:
            continue
        for loc in _sitemap_locs(nested):
            if _same_dr_alban_host(loc, origin_netloc) and not loc.lower().endswith(".xml"):
                pages.append(loc)
    return list(dict.fromkeys(pages))


def _dr_alban_http_sitemap_fallback(*, max_pages: int = 7, total_budget: int = 24_000) -> str:
    """Fetch albanandrieu.com pages discovered via sitemap when web search is unavailable."""
    origin = _dr_alban_origin()
    origin_netloc = urlparse(origin).netloc
    seed_locs: list[str] = []
    for path in ("sitemap.xml", "sitemap_index.xml"):
        sm_url = urljoin(origin + "/", path)
        try:
            xml_body = _http_get_text(sm_url)
        except OSError:
            continue
        seed_locs = _sitemap_locs(xml_body)
        if seed_locs:
            break
    page_urls = _expand_sitemap_to_page_urls(seed_locs, origin_netloc=origin_netloc)
    ordered = list(dict.fromkeys([PROFESSIONAL_WEBSITE_URL, *page_urls]))
    chunks: list[str] = []
    used = 0
    for url in ordered[:max_pages]:
        try:
            html = _http_get_text(url)
        except OSError as exc:
            logger.warning("fetch_my_profile: sitemap fallback fetch failed for %s: %s", url, exc)
            chunks.append(f"URL: {url}\n(fetch failed)\n")
            continue
        room = max(0, total_budget - used)
        if room <= 0:
            break
        text = _html_to_visible_text(html, max_chars=min(6000, room))
        used += len(text)
        chunks.append(f"URL: {url}\n\n{text}\n")
    body = "\n---\n".join(chunks).strip()
    return body or f"Could not extract readable text from {PROFESSIONAL_WEBSITE_URL}."


def _web_search_profile_blocks() -> str | None:
    """Return text from configured search APIs, or None to use HTTP fallback."""
    if resolve_web_search_provider() is None:
        return None
    max_results = get_settings().web_search_max_results
    primary_q = f'Alban Andrieu professional profile site:albanandrieu.com "{PROFESSIONAL_WEBSITE_URL}"'
    linkedin_queries = (
        "Alban Andrieu site:linkedin.com/in/nabla",
        f'Alban Andrieu DevSecOps site:linkedin.com "{LINKEDIN_URL}"',
    )
    blocks: list[str] = []
    primary_text = ""
    try:
        primary_text = web_search_to_context_string(primary_q, max_results=max_results).strip()
    except Exception as exc:
        logger.warning("fetch_my_profile: albanandrieu.com web search failed: %s", exc)
    if primary_text:
        blocks.append(f"Web search — albanandrieu.com\n{primary_text}")
    for query in linkedin_queries:
        try:
            linked = web_search_to_context_string(query, max_results=max_results).strip()
        except Exception as exc:
            logger.warning("fetch_my_profile: LinkedIn web search failed: %s", exc)
            linked = ""
        if linked:
            blocks.append(f"Web search — LinkedIn ({LINKEDIN_URL})\n{linked}")
            break
    if not blocks:
        return None
    return "\n\n---\n\n".join(blocks)


def _resume_text(data: dict) -> str:
    """Flatten the visible CV sections to ``section — field: value`` lines."""
    basics = data.get("basics") or {}
    lines = [", ".join(f"{key}: {value}" for key, value in basics.items() if key not in _RESUME_SKIP and isinstance(value, str) and value)]
    lines.append(_html_to_visible_text((data.get("summary") or {}).get("content") or ""))
    for name, section in (data.get("sections") or {}).items():
        if not isinstance(section, dict) or section.get("hidden"):
            continue
        for item in section.get("items") or []:
            if item.get("hidden"):
                continue
            fields = []
            for key, value in item.items():
                text = ", ".join(map(str, value)) if isinstance(value, list) else value
                if key not in _RESUME_SKIP and isinstance(text, str) and text:
                    fields.append(f"{key}: {_html_to_visible_text(text, max_chars=1500)}")
            lines.append(f"{name} — " + "; ".join(fields))
    return "\n".join(line for line in lines if line)[:12_000]


def _reactive_resume_block() -> str | None:
    """Return the public CV text, or None outside the homelab or on any failure."""
    from nabla.api.runtime_environment import homelab_runtime_detected  # noqa: PLC0415 -- LAN-only source

    if not homelab_runtime_detected():
        return None
    try:
        text = _resume_text(json.loads(_http_get_text(_REACTIVE_RESUME_API, timeout=10.0))["data"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        logger.warning("fetch_my_profile: Reactive Resume unavailable: %s", exc)
        return None
    return f"Reactive Resume CV ({REACTIVE_RESUME_URL})\n{text}" if text else None


def search_alban_profile_context(user_question: str) -> str:
    """Return verified public profile context for an Alban Andrieu question."""
    if not user_question or not user_question.strip():
        return "Missing `user_question`. Pass the user's question verbatim."
    if not question_refers_to_alban_profile(user_question):
        return "Skipped profile search: the question does not appear to be about Alban Andrieu."
    search_block = _web_search_profile_blocks()
    web = (
        f"Web search ({PROFESSIONAL_WEBSITE_URL}; LinkedIn {LINKEDIN_URL}):\n\n{search_block}"
        if search_block
        else f"Direct HTTP + sitemap of {PROFESSIONAL_WEBSITE_URL} (no web search configured or no results):\n\n{_dr_alban_http_sitemap_fallback()}"
    )
    return "Profile context:\n\n" + "\n\n---\n\n".join(block for block in (_reactive_resume_block(), web) if block)


@tool
def fetch_my_profile(user_question: str | None = None) -> str:
    """Load Alban Andrieu's public profile for the LangChain workflow."""
    return search_alban_profile_context(user_question or "")


def runtime_whoami() -> str:
    """Return the current OS login name (equivalent to the ``whoami`` command)."""
    return os.environ.get("USER") or os.environ.get("USERNAME") or getpass.getuser()


def get_me() -> UserIn:
    """👤 Return the canonical profile for Alban Andrieu."""
    return UserIn(
        user_id=WHOAMI_HANDLE,
        name=DISPLAY_NAME,
        email=EMAIL,
        phone=PHONE,
        address=ADDRESS,
        city=CITY,
        state=STATE,
        zipcode=ZIPCODE,
        country=COUNTRY,
    )
