"""Regression coverage for credential-safe runtime logging."""

import logging

from nabla.utils.log_config import SensitiveLogFilter, sanitize_log_value


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
