"""Regression tests for Polars/Chrono sensor timestamp parsing."""

import warnings

from nabla.api.demo import models


def test_sensor_dataframe_parses_fractional_seconds_without_chrono_warning(monkeypatch):
    monkeypatch.setattr(
        models,
        "recent_readings",
        [
            {
                "timestamp": "2026-08-05T18:29:28.123456",
                "temperature": 21.3,
                "humidity": 53.8,
                "pressure": 1003.0,
                "status": "normal",
            },
        ],
    )

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        frame = models.get_sensor_dataframe()

    assert frame.height == 1
    assert frame["timestamp"].dtype == models.pl.Datetime("us")
