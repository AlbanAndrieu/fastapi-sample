"""Unit-test environment isolation contracts."""

import os


def test_unit_suite_disables_external_telemetry() -> None:
    for key in (
        "METRICS_ENABLED",
        "LOGFIRE_ENABLED",
        "SENTRY_ENABLED",
        "DATADOG_ENABLED",
        "UNLEASH_ENABLED",
        "STATSIG_ENABLED",
        "DD_TRACE_ENABLED",
        "DD_PROFILING_ENABLED",
    ):
        assert os.environ[key] == "false"

    assert os.environ["LOGFIRE_TOKEN"] == ""
    assert os.environ["SENTRY_DSN"] == ""
    assert os.environ["SENTRY_LOCAL_DSN"] == ""
