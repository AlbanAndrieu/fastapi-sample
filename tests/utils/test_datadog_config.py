"""Tests for optional Datadog runtime integration."""

import builtins
from pathlib import Path
from unittest.mock import Mock

from nabla.utils import datadog_config


def test_datadog_disabled_does_not_import_sdk(monkeypatch):
    """Disabled Datadog must not import ddtrace or add startup overhead."""
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.startswith("ddtrace"):
            raise AssertionError("ddtrace must not be imported while disabled")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    assert datadog_config.configure_datadog(enabled=False, app_name="test") is False
    assert (
        datadog_config.start_datadog_profiler(enabled=False, app_name="test") is None
    )
    with datadog_config.datadog_trace(enabled=False, name="test") as span:
        assert span is None


def test_missing_datadog_is_non_fatal(monkeypatch):
    """An explicitly enabled but absent SDK must degrade gracefully."""
    real_import = builtins.__import__

    def missing_ddtrace(name, *args, **kwargs):
        if name.startswith("ddtrace"):
            raise ModuleNotFoundError("No module named 'ddtrace'", name="ddtrace")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_ddtrace)
    assert datadog_config.configure_datadog(enabled=True, app_name="test") is False


def test_profiler_is_owned_by_application_lifespan(monkeypatch):
    """The acquired profiler handle can be stopped deterministically."""
    profiler = Mock()
    profiler_cls = Mock(return_value=profiler)
    monkeypatch.setattr(datadog_config, "_load_profiler", lambda: profiler_cls)

    handle = datadog_config.start_datadog_profiler(
        enabled=True,
        app_name="test",
    )
    datadog_config.stop_datadog_profiler(handle)

    profiler_cls.assert_called_once_with(env="prod", service="test")
    profiler.start.assert_called_once()
    profiler.stop.assert_called_once()


def test_runtime_modules_have_no_direct_ddtrace_imports():
    """Disabled runtime imports must not load Datadog through route modules."""
    runtime_modules = (
        "nabla/api/db/database.py",
        "nabla/api/v1.py",
        "nabla/api/ping.py",
        "nabla/api/demo/integration.py",
    )

    for module_path in runtime_modules:
        source = Path(module_path).read_text(encoding="utf-8")
        assert "from ddtrace" not in source
        assert "import ddtrace" not in source
