"""Regression tests for bounded external-probe Prometheus metrics."""

from nabla.api import probe_metrics


def _series(metric) -> set[tuple[tuple[str, str], ...]]:
    return {
        tuple(sorted(sample.labels.items()))
        for family in metric.collect()
        for sample in family.samples
    }


def _counter_value(metric, **labels) -> float:
    samples = metric.labels(**labels).collect()[0].samples
    return next(
        float(sample.value)
        for sample in samples
        if sample.name.endswith("_total")
    )


def _gauge_value(metric, **labels) -> float:
    if labels:
        samples = metric.labels(**labels).collect()[0].samples
    else:
        samples = metric.collect()[0].samples
    return float(samples[0].value)


def test_unknown_labels_do_not_create_metric_series() -> None:
    provider_series = _series(probe_metrics.PROVIDER_OUTCOMES)
    cache_series = _series(probe_metrics.CACHE_OUTCOMES)
    timeout_series = _series(probe_metrics.PROBE_TIMEOUTS)

    probe_metrics.record_provider_outcome("https://dynamic.example", "failure")
    probe_metrics.record_cache_outcome("cache-key:user-controlled")
    probe_metrics.record_probe_timeout("https://dynamic.example")

    assert _series(probe_metrics.PROVIDER_OUTCOMES) == provider_series
    assert _series(probe_metrics.CACHE_OUTCOMES) == cache_series
    assert _series(probe_metrics.PROBE_TIMEOUTS) == timeout_series


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
        _gauge_value(
            probe_metrics.CIRCUIT_STATE,
            provider="truenas",
            state="open",
        )
        == 1
    )
    assert (
        _gauge_value(
            probe_metrics.CIRCUIT_STATE,
            provider="truenas",
            state="closed",
        )
        == 0
    )


def test_probe_in_flight_gauge_balances() -> None:
    before = _gauge_value(probe_metrics.PROBES_IN_FLIGHT)
    probe_metrics.probe_started()
    assert _gauge_value(probe_metrics.PROBES_IN_FLIGHT) == before + 1
    probe_metrics.probe_finished()
    assert _gauge_value(probe_metrics.PROBES_IN_FLIGHT) == before
