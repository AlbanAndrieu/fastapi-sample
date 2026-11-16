"""F08: each create_app phase logs its duration and a slow one is a warning."""

from __future__ import annotations

import pytest
from structlog.testing import capture_logs

from nabla import startup_phases
from nabla.app_factory import create_app
from nabla.app_features import AppFeatures


def test_slow_phase_is_a_warning_and_failing_phase_is_still_timed(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = iter([10.0, 16.5])
    monkeypatch.setattr(startup_phases.time, "perf_counter", lambda: next(clock))
    with capture_logs() as logs, pytest.raises(RuntimeError), startup_phases.startup_phase("sentry"):
        raise RuntimeError("boom")
    assert logs == [
        {"event": "startup_phase", "phase": "sentry", "duration_ms": 6500, "slow": True, "log_level": "warning"},
    ]


def test_create_app_names_each_phase() -> None:
    with capture_logs() as logs:
        create_app(AppFeatures.minimal())
    phases = [entry["phase"] for entry in logs if entry["event"] == "startup_phase"]
    assert phases[0] == "process_start_to_create_app"
    assert {"rate_limiting", "unleash", "routers", "routes"} <= set(phases)
