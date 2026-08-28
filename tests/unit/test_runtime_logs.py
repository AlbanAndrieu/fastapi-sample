"""Tests for local MCP runtime log capture."""

from __future__ import annotations

import logging

from nabla.utils.runtime_logs import (
    RuntimeLogHandler,
    capture_structlog_event,
    clear_runtime_logs,
    get_runtime_errors,
    get_runtime_logs,
    runtime_diagnostics_enabled,
)


def test_runtime_diagnostics_auto_enable_for_reload(monkeypatch) -> None:
    monkeypatch.delenv("RUNTIME_DIAGNOSTICS_ENABLED", raising=False)
    monkeypatch.setattr("sys.argv", ["gunicorn", "server_all:app", "--reload"])

    assert runtime_diagnostics_enabled() is True


def test_explicit_false_disables_reload_diagnostics(monkeypatch) -> None:
    monkeypatch.setenv("RUNTIME_DIAGNOSTICS_ENABLED", "false")
    monkeypatch.setattr("sys.argv", ["gunicorn", "server_all:app", "--reload"])

    assert runtime_diagnostics_enabled() is False


def test_runtime_logs_are_redacted_and_filterable(monkeypatch) -> None:
    monkeypatch.setenv("RUNTIME_DIAGNOSTICS_ENABLED", "true")
    clear_runtime_logs()

    event = {
        "event": "request failed token=super-secret",
        "level": "error",
        "api_key": "do-not-expose",
        "path": "/demo",
    }
    returned = capture_structlog_event(None, "error", event)

    assert returned is event
    logs = get_runtime_logs(limit=10, contains="request failed")
    assert len(logs) == 1
    serialized = repr(logs)
    assert "super-secret" not in serialized
    assert "do-not-expose" not in serialized
    assert "[REDACTED]" in serialized
    assert get_runtime_errors(limit=10) == logs


def test_stdlib_handler_masks_bearer_tokens(monkeypatch) -> None:
    monkeypatch.setenv("RUNTIME_DIAGNOSTICS_ENABLED", "true")
    clear_runtime_logs()
    handler = RuntimeLogHandler()
    record = logging.LogRecord(
        name="uvicorn.error",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="upstream rejected Authorization: Bearer abc.def.ghi",
        args=(),
        exc_info=None,
    )

    handler.emit(record)

    logs = get_runtime_errors(limit=10)
    assert len(logs) == 1
    serialized = repr(logs)
    assert "abc.def.ghi" not in serialized
    assert "[REDACTED]" in serialized


def test_disabled_runtime_diagnostics_capture_nothing(monkeypatch) -> None:
    monkeypatch.setenv("RUNTIME_DIAGNOSTICS_ENABLED", "false")
    clear_runtime_logs()

    capture_structlog_event(None, "error", {"event": "must not be captured"})

    assert get_runtime_logs(limit=10) == []
