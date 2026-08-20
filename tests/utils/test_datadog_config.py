"""Tests for optional Datadog runtime integration."""

import builtins

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


def test_missing_datadog_is_non_fatal(monkeypatch):
    """An explicitly enabled but absent SDK must degrade gracefully."""
    real_import = builtins.__import__

    def missing_ddtrace(name, *args, **kwargs):
        if name.startswith("ddtrace"):
            raise ModuleNotFoundError("No module named 'ddtrace'", name="ddtrace")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_ddtrace)
    assert datadog_config.configure_datadog(enabled=True, app_name="test") is False
