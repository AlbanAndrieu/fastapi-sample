"""Small HTML post-processing helpers for the API health board.

The health board JavaScript still lives in the legacy, oversized ``ui.py`` module.
Keep narrowly-scoped ordering changes here until that UI is split into dedicated
static assets.
"""

from __future__ import annotations


_TRUENAS_CHECK_KEY = "albandrieu_truenas"
_HEALTH_PRIORITY_ANCHOR = '                "albandrieu_vaultwarden",\n                "litellm",'
_HEALTH_PRIORITY_WITH_PLATFORMS = (
    '                "albandrieu_vaultwarden",\n'
    f'                "{_TRUENAS_CHECK_KEY}",\n'
    '                "cloudflare",\n'
    '                "pfsense",\n'
    '                "litellm",'
)
_LABEL_ANCHOR = '            litellm: "LiteLLM proxy",'
_LABELS_WITH_PLATFORMS = (
    '            litellm: "LiteLLM proxy",\n'
    '            cloudflare: "Cloudflare Tunnels",\n'
    '            pfsense: "pfSense API",'
)


def prioritize_optional_truenas(html: str) -> str:
    """Place TrueNAS, Cloudflare and pfSense after required health checks.

    These keys deliberately stay out of the JavaScript ``MANDATORY`` set. The
    transformation only changes display order and labels: failures remain optional
    integration failures and therefore degrade the board instead of failing core
    FastAPI health in red.
    """
    result = html
    if _HEALTH_PRIORITY_WITH_PLATFORMS not in result and _HEALTH_PRIORITY_ANCHOR in result:
        result = result.replace(
            _HEALTH_PRIORITY_ANCHOR,
            _HEALTH_PRIORITY_WITH_PLATFORMS,
            1,
        )
    if _LABELS_WITH_PLATFORMS not in result and _LABEL_ANCHOR in result:
        result = result.replace(_LABEL_ANCHOR, _LABELS_WITH_PLATFORMS, 1)
    return result
