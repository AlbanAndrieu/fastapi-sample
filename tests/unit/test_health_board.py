"""Tests for the API health-board ordering contract."""

from nabla.api.health_board import prioritize_optional_truenas
from nabla.api.ui import render_api_root_page


def test_truenas_is_ordered_after_required_checks_and_before_optional_litellm() -> None:
    page = prioritize_optional_truenas(
        render_api_root_page(title_suffix="test", app_version="test")
    )

    required = page.index('"albandrieu_vaultwarden",')
    truenas = page.index('"albandrieu_truenas",')
    litellm = page.index('"litellm",', truenas)

    assert required < truenas < litellm


def test_truenas_is_not_mandatory() -> None:
    page = prioritize_optional_truenas(
        render_api_root_page(title_suffix="test", app_version="test")
    )
    mandatory_start = page.index("const MANDATORY = new Set([")
    mandatory_end = page.index("]);", mandatory_start)
    mandatory_block = page[mandatory_start:mandatory_end]

    assert '"albandrieu_truenas"' not in mandatory_block


def test_prioritization_is_idempotent() -> None:
    page = render_api_root_page(title_suffix="test", app_version="test")

    once = prioritize_optional_truenas(page)
    twice = prioritize_optional_truenas(once)

    assert once == twice
    assert once.count('"albandrieu_truenas",') == 1
