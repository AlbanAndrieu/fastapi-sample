"""Regression tests for bounded external-probe Prometheus metrics."""

from nabla.api import probe_metrics


def _counter_value(metric, **labels) -> float:
    return float(metric.labels(**labels)._value.get())


def test_unknown_labels_do_not_create_metric_series() -> None:
    provider_series = set(probe_metrics.PROVIDER_OUTCOMES._metrics)
    cache_series = set(probe_metrics.CACHE_OUTCOMES._metrics)
    timeout_series = set(probe_metrics.PROBE_TIMEOUTS._metrics)

    probe_metrics.record_provider_outcome("https://dynamic.example", "failure")
    probe_metrics.record_cache_outcome("cache-key:user-controlled")
    probe_metrics.record_probe_timeout("https://dynamic.example")

    assert set(probe_metrics.PROVIDER_OUTCOMES._metrics) == provider_series
    assert set(probe_metrics.CACHE_OUTCOMES._metrics) == cache_series
    assert set(probe_metrics.PROBE_TIMEOUTS._metrics) == timeout_series


def test_provider_outcome_and_circuit_state_use_fixed_labels() -> None:
    before = _counter_value(
        probe_metrics.PROVIDER_OUTCOMES,
        provider="truenas",
        outcome="success",
    )
    probe_metrics.record_provider_outcome("truenas", "success")
    probe_metrics.record_circuit_state("truenas", "open")

    assert (
        _counter_value(
            probe_metrics.PROVIDER_OUTCOMES,
            provider="truenas",
            outcome="success",
        )
        == before + 1
    )
    assert (
        probe_metrics.CIRCUIT_STATE.labels(provider="truenas", state="open")._value.get()
        == 1
    )
    assert (
        probe_metrics.CIRCUIT_STATE.labels(
            provider="truenas", state="closed"
        )._value.get()
        == 0
    )


def test_probe_in_flight_gauge_balances() -> None:
    before = float(probe_metrics.PROBES_IN_FLIGHT._value.get())
    probe_metrics.probe_started()
    assert float(probe_metrics.PROBES_IN_FLIGHT._value.get()) == before + 1
    probe_metrics.probe_finished()
    assert float(probe_metrics.PROBES_IN_FLIGHT._value.get()) == before
