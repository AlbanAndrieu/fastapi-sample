"""Regression coverage for secret-safe structured logging."""

from nabla.utils.logger import _REDACTED, _redact_value


def test_short_password_label_is_redacted() -> None:
    assert _redact_value("Postgres pass: example-secret") == (f"Postgres pass: {_REDACTED}")


def test_connection_string_credentials_are_redacted() -> None:
    scheme = "postgresql"
    connection_url = f"{scheme}://demo:example-secret@db.example.test/app"

    assert _redact_value(connection_url) == (f"{scheme}://demo:{_REDACTED}@db.example.test/app")


def test_nested_short_password_field_is_redacted() -> None:
    assert _redact_value({"database": {"pass": "example-secret"}}) == {
        "database": {"pass": _REDACTED},
    }
