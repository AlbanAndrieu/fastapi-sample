"""Regression coverage for credential-safe runtime logging."""

import logging

from nabla.utils.log_config import (
    HealthCheckFilter,
    MetricsFilter,
    SensitiveLogFilter,
    configure_library_log_levels,
    sanitize_log_value,
)
from nabla.utils.logger import add_user_id


def test_sanitizer_removes_url_credentials_query_and_fragment() -> None:
    raw = "GET https://user:password@example.test/path?token=signed-value#fragment"

    sanitized = sanitize_log_value(raw)

    assert sanitized == "GET https://example.test/path?[REDACTED]"
    assert "password" not in sanitized
    assert "signed-value" not in sanitized


def test_log_filter_scrubs_structured_request_and_bearer_token() -> None:
    record = logging.LogRecord(
        "test",
        logging.INFO,
        __file__,
        1,
        "Authorization: Bearer very-secret",
        (),
        None,
    )
    record.req = {
        "url": "https://example.test/api?meta=signed",
        "authorization": "Bearer secret",
    }

    assert SensitiveLogFilter().filter(record) is True
    assert record.getMessage() == "Authorization: Bearer [REDACTED]"
    assert record.req["url"] == "https://example.test/api?[REDACTED]"
    assert record.req["authorization"] == "[REDACTED]"


def test_library_log_levels_suppress_unleash_polling_info() -> None:
    configure_library_log_levels()

    assert logging.getLogger("UnleashClient").getEffectiveLevel() >= logging.WARNING


def test_structured_log_identity_defaults_to_anonymous() -> None:
    event = add_user_id(None, None, {})

    assert event["user_id"] == "anonymous"


def test_structured_log_identity_preserves_authenticated_user() -> None:
    event = add_user_id(None, None, {"user_id": "principal-42"})

    assert event["user_id"] == "principal-42"


def _access_record(message: str) -> logging.LogRecord:
    return logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        message,
        (),
        None,
    )


def test_metrics_filter_drops_scrapes_but_keeps_application_requests() -> None:
    access_filter = MetricsFilter()

    assert (
        access_filter.filter(
            _access_record('127.0.0.1 - "GET /metrics HTTP/1.1" 200')
        )
        is False
    )
    assert access_filter.filter(
        _access_record('127.0.0.1 - "GET /metrics?format=openmetrics HTTP/1.1" 200')
    ) is False
    assert (
        access_filter.filter(_access_record('127.0.0.1 - "GET /api HTTP/1.1" 200'))
        is True
    )
    assert access_filter.filter(
        _access_record('127.0.0.1 - "GET /api/health-board HTTP/1.1" 200')
    ) is True


def test_health_filter_drops_operational_probes_but_keeps_api_requests() -> None:
    access_filter = HealthCheckFilter()

    for path in ("/health", "/healthz", "/livez", "/readyz", "/sickz"):
        assert access_filter.filter(
            _access_record(f'127.0.0.1 - "GET {path} HTTP/1.1" 200')
        ) is False
    assert (
        access_filter.filter(_access_record('127.0.0.1 - "GET /api HTTP/1.1" 200'))
        is True
    )
    assert (
        access_filter.filter(
            _access_record('127.0.0.1 - "GET /api/health-board HTTP/1.1" 200')
        )
        is True
    )
