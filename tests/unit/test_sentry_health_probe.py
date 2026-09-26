"""Regression tests for Sentry health target selection."""

from nabla.api import integration_health


def test_local_sentry_outage_is_not_masked_by_cloud_fallback(monkeypatch) -> None:
    local_dsn = "http://local-public@172.17.0.24:9005/2"
    monkeypatch.setenv("SENTRY_LOCAL_DSN", local_dsn)
    monkeypatch.setenv(
        "SENTRY_DSN",
        "https://cloud-public@example.ingest.sentry.io/42",
    )
    observed: list[str] = []

    def reachable(dsn: str) -> bool:
        observed.append(dsn)
        return False

    monkeypatch.setattr(integration_health, "sentry_dsn_is_reachable", reachable)

    result = integration_health.probe_sentry_reachable()

    assert result == {
        "reachable": False,
        "target": "local",
        "probe": "dsn_socket",
    }
    assert observed == [local_dsn]


def test_sentry_health_is_skipped_without_explicit_health_target(monkeypatch) -> None:
    monkeypatch.delenv("SENTRY_LOCAL_DSN", raising=False)
    monkeypatch.delenv("SENTRY_DSN", raising=False)

    result = integration_health.probe_sentry_reachable()

    assert result["reachable"] is None
    assert result["skipped"] is True
