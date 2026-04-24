"""Sentry event filters used to reduce low-signal noise."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def _argv_looks_like_pytest(argv: object) -> bool:
    """Return whether argv includes a pytest invocation."""
    if not isinstance(argv, Sequence) or isinstance(argv, str | bytes | bytearray):
        return False
    return any(isinstance(item, str) and "pytest" in item.lower() for item in argv)


def should_drop_non_prod_test_event(event: Mapping[str, Any]) -> bool:
    """Return whether the Sentry event matches local test noise signatures."""
    request = event.get("request")
    if isinstance(request, Mapping):
        request_url = request.get("url")
        if isinstance(request_url, str) and request_url.startswith("http://testserver/"):
            return True

    extra = event.get("extra")
    if isinstance(extra, Mapping) and _argv_looks_like_pytest(extra.get("sys.argv")):
        return True

    return False


def before_send_filter_test_noise(
    event: dict[str, Any],
    hint: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Drop synthetic test-client errors before they are sent to Sentry."""
    del hint
    if should_drop_non_prod_test_event(event):
        return None
    return event
