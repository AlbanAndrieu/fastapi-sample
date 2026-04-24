"""Unit tests for Sentry event noise filters."""

from typing import Any

from nabla.utils.sentry_filters import (
    before_send_filter_test_noise,
    should_drop_non_prod_test_event,
)


def test_should_drop_event_from_testserver_url() -> None:
    event: dict[str, Any] = {
        "request": {"url": "http://testserver/v1/tavily/search"},
        "extra": {},
    }
    assert should_drop_non_prod_test_event(event) is True


def test_should_drop_event_with_pytest_argv() -> None:
    event: dict[str, Any] = {
        "request": {"url": "https://fastapi-sample.fastapicloud.dev/v1/tavily/search"},
        "extra": {"sys.argv": ["/venv/bin/pytest", "tests/unit/test_api.py"]},
    }
    assert should_drop_non_prod_test_event(event) is True


def test_should_not_drop_real_production_event() -> None:
    event: dict[str, Any] = {
        "request": {"url": "https://fastapi-sample.fastapicloud.dev/v1/tavily/search"},
        "extra": {"sys.argv": ["gunicorn", "main:app"]},
    }
    assert should_drop_non_prod_test_event(event) is False


def test_before_send_drops_noise_event() -> None:
    event: dict[str, Any] = {
        "request": {"url": "http://testserver/v1/tavily/search"},
        "extra": {"sys.argv": ["pytest", "tests/unit/test_api.py"]},
    }
    assert before_send_filter_test_noise(event=event, hint={}) is None


def test_before_send_keeps_non_noise_event() -> None:
    event: dict[str, Any] = {
        "request": {"url": "https://fastapi-sample.fastapicloud.dev/v1/tavily/search"},
        "extra": {"sys.argv": ["uvicorn", "main:app"]},
    }
    assert before_send_filter_test_noise(event=event, hint={}) == event
