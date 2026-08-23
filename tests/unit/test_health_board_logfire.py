"""Ordering contract for optional Logfire health-board rendering."""

from nabla.api.health_board import prioritize_optional_truenas
from nabla.api.ui import render_api_root_page


def test_logfire_is_optional_and_rendered_immediately_below_sentry() -> None:
    page = prioritize_optional_truenas(
        render_api_root_page(title_suffix="test", app_version="test")
    )

    sentry = page.index('"sentry",')
    logfire = page.index('"logfire",', sentry)
    mandatory_start = page.index("const MANDATORY = new Set([")
    mandatory_end = page.index("]);", mandatory_start)

    assert sentry < logfire
    assert '"logfire"' not in page[mandatory_start:mandatory_end]
    assert 'logfire: "Pydantic Logfire"' in page
