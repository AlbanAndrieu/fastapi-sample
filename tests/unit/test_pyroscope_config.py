"""Tests for the process-local Pyroscope profiler lifecycle."""

from unittest.mock import Mock

from nabla.utils import pyroscope_config


def test_start_pyroscope_skips_when_disabled(monkeypatch) -> None:
    configure = Mock()
    monkeypatch.setattr(pyroscope_config.pyroscope, "configure", configure)

    started = pyroscope_config.start_pyroscope(
        enabled=False,
        application_name="fastapi-sample",
        server_address="http://172.17.0.24:4040",
    )

    assert started is False
    configure.assert_not_called()


def test_start_pyroscope_configures_worker_profiler(monkeypatch) -> None:
    configure = Mock()
    monkeypatch.setattr(pyroscope_config.pyroscope, "configure", configure)

    started = pyroscope_config.start_pyroscope(
        enabled=True,
        application_name="fastapi-sample",
        server_address="http://172.17.0.24:4040",
    )

    assert started is True
    configure.assert_called_once_with(
        application_name="fastapi-sample",
        server_address="http://172.17.0.24:4040",
        sample_rate=100,
        enable_logging=True,
    )


def test_start_pyroscope_failure_is_non_fatal(monkeypatch) -> None:
    configure = Mock(side_effect=RuntimeError("backend unavailable"))
    monkeypatch.setattr(pyroscope_config.pyroscope, "configure", configure)

    started = pyroscope_config.start_pyroscope(
        enabled=True,
        application_name="fastapi-sample",
        server_address="http://172.17.0.24:4040",
    )

    assert started is False


def test_stop_pyroscope_only_shuts_down_started_profiler(monkeypatch) -> None:
    shutdown = Mock()
    monkeypatch.setattr(pyroscope_config.pyroscope, "shutdown", shutdown)

    pyroscope_config.stop_pyroscope(False)
    shutdown.assert_not_called()

    pyroscope_config.stop_pyroscope(True)
    shutdown.assert_called_once_with()
