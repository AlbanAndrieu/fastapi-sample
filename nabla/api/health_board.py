"""Small HTML post-processing helpers for the API health board.

The health board JavaScript still lives in the legacy, oversized ``ui.py`` module.
Keep narrowly-scoped ordering changes here until that UI is split into dedicated
static assets.
"""

from __future__ import annotations


_TRUENAS_CHECK_KEY = "albandrieu_truenas"
_HEALTH_PRIORITY_ANCHOR = '                "albandrieu_vaultwarden",\n                "litellm",'
_HEALTH_PRIORITY_WITH_TRUENAS = (
    '                "albandrieu_vaultwarden",\n'
    f'                "{_TRUENAS_CHECK_KEY}",\n'
    '                "litellm",'
)


def prioritize_optional_truenas(html: str) -> str:
    """Place TrueNAS immediately after required health checks.

    ``albandrieu_truenas`` deliberately stays out of the JavaScript ``MANDATORY``
    set. The transformation only changes display order: a failed TrueNAS probe
    remains an optional integration failure and therefore degrades the board to
    yellow instead of failing the core FastAPI health in red.
    """
    if _HEALTH_PRIORITY_WITH_TRUENAS in html:
        return html
    if _HEALTH_PRIORITY_ANCHOR not in html:
        return html
    return html.replace(
        _HEALTH_PRIORITY_ANCHOR,
        _HEALTH_PRIORITY_WITH_TRUENAS,
        1,
    )
