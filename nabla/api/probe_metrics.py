"""Fixed-cardinality Prometheus metrics for external diagnostic probes."""

from __future__ import annotations

import math

from prometheus_client import Counter, Gauge, Histogram

_PROVIDERS = frozenset({"truenas", "pfsense", "cloudflare"})
_PROVIDER_OUTCOMES = frozenset({"success", "failure", "suppressed"})
_ORIGIN_OUTCOMES = frozenset({"success", "failure"})
_CIRCUIT_STATES = ("closed", "open", "half_open")
_CACHE_OUTCOMES = frozenset(
    {"l1_hit", "redis_hit", "local_hit", "miss", "stale", "redis_degraded"}
)
_TIMEOUT_PHASES = frozenset({"deadline", "queue", "origin"})
_PFSENSE_PREFLIGHT_OUTCOMES = frozenset({"success", "auth_rejected", "failure"})
_PFSENSE_PROTECTIVE_SKIP_REASONS = frozenset(
    {"slow_preflight", "authentication_failure"},
)
_PFSENSE_REQUEST_PHASES = frozenset({"preflight", "deep"})

PROVIDER_OUTCOMES = Counter(
    "nabla_external_provider_outcomes_total",
    "External provider probe outcomes.",
    ("provider", "outcome"),
)
PROVIDER_BUDGET_REJECTIONS = Counter(
    "nabla_external_provider_rate_budget_rejections_total",
    "External provider origin attempts suppressed by the rate budget.",
    ("provider",),
)
PROVIDER_RATE_BUDGET_UTILIZATION = Gauge(
    "nabla_external_provider_rate_budget_utilization_ratio",
    "Observed provider attempts divided by the configured fixed-window rate budget.",
    ("provider",),
)
PROVIDER_ORIGIN_DURATION = Histogram(
    "nabla_external_provider_origin_duration_seconds",
    "External provider origin probe duration.",
    ("provider", "outcome"),
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0),
)
PROVIDER_ORIGINS_IN_FLIGHT = Gauge(
    "nabla_external_provider_origins_in_flight",
    "External provider origin probes currently executing.",
    ("provider",),
)
CIRCUIT_STATE = Gauge(
    "nabla_external_provider_circuit_state",
    "Current provider circuit state as a one-hot gauge.",
    ("provider", "state"),
)
CACHE_OUTCOMES = Counter(
    "nabla_external_probe_cache_outcomes_total",
    "External probe cache outcomes.",
    ("outcome",),
)
ORIGIN_REFRESHES = Counter(
    "nabla_external_probe_origin_refreshes_total",
    "External probe origin refreshes.",
)
PROBE_TIMEOUTS = Counter(
    "nabla_external_probe_timeouts_total",
    "Diagnostic probe deadline expirations.",
    ("phase",),
)
PROBES_IN_FLIGHT = Gauge(
    "nabla_external_probes_in_flight",
    "Diagnostic probes currently executing under a request budget.",
)
PFSENSE_PREFLIGHT_DURATION = Histogram(
    "nabla_pfsense_preflight_duration_seconds",
    "Duration of the pfSense system.version preflight before deep posture fan-out.",
    ("outcome",),
    buckets=(0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 6.0, 8.0),
)
PFSENSE_PROTECTIVE_SKIPS = Counter(
    "nabla_pfsense_protective_skips_total",
    "pfSense posture fan-out skips triggered to protect the appliance.",
    ("reason",),
)
PFSENSE_API_REQUESTS = Counter(
    "nabla_pfsense_api_requests_total",
    "pfSense posture API requests actually started.",
    ("phase",),
)
PFSENSE_API_REQUESTS_IN_FLIGHT = Gauge(
    "nabla_pfsense_api_requests_in_flight",
    "pfSense posture API requests currently executing.",
    ("phase",),
)


def record_provider_outcome(provider: str | None, outcome: str) -> None:
    """Record only pre-approved provider/outcome label values."""
    if provider in _PROVIDERS and outcome in _PROVIDER_OUTCOMES:
        PROVIDER_OUTCOMES.labels(provider=provider, outcome=outcome).inc()


def record_provider_budget_rejection(provider: str | None) -> None:
    """Record only bounded provider labels for rate-budget suppression."""
    if provider in _PROVIDERS:
        PROVIDER_BUDGET_REJECTIONS.labels(provider=provider).inc()


def record_provider_rate_budget_utilization(
    provider: str | None,
    *,
    count: int,
    max_requests: int,
) -> None:
    """Expose fixed-cardinality budget pressure without claiming a safe capacity."""
    if provider not in _PROVIDERS or count < 0 or max_requests < 1:
        return
    PROVIDER_RATE_BUDGET_UTILIZATION.labels(provider=provider).set(
        count / max_requests
    )


def observe_provider_origin_duration(
    provider: str | None,
    *,
    outcome: str,
    duration_seconds: float,
) -> None:
    """Observe bounded provider origin latency for capacity correlation."""
    if provider not in _PROVIDERS or outcome not in _ORIGIN_OUTCOMES:
        return
    if not math.isfinite(duration_seconds) or duration_seconds < 0:
        return
    PROVIDER_ORIGIN_DURATION.labels(provider=provider, outcome=outcome).observe(
        duration_seconds
    )


def provider_origin_started(provider: str | None) -> None:
    """Increment current origin work for one bounded provider."""
    if provider in _PROVIDERS:
        PROVIDER_ORIGINS_IN_FLIGHT.labels(provider=provider).inc()


def provider_origin_finished(provider: str | None) -> None:
    """Decrement current origin work for one bounded provider."""
    if provider in _PROVIDERS:
        PROVIDER_ORIGINS_IN_FLIGHT.labels(provider=provider).dec()


def record_circuit_state(provider: str | None, state: str) -> None:
    """Set one fixed provider circuit state without dynamic labels."""
    if provider not in _PROVIDERS or state not in _CIRCUIT_STATES:
        return
    for candidate in _CIRCUIT_STATES:
        CIRCUIT_STATE.labels(provider=provider, state=candidate).set(
            1 if candidate == state else 0
        )


def record_cache_outcome(outcome: str) -> None:
    """Record one bounded cache outcome."""
    if outcome in _CACHE_OUTCOMES:
        CACHE_OUTCOMES.labels(outcome=outcome).inc()


def record_origin_refresh() -> None:
    """Record one origin refresh attempt."""
    ORIGIN_REFRESHES.inc()


def record_probe_timeout(phase: str) -> None:
    """Record one bounded timeout phase."""
    if phase in _TIMEOUT_PHASES:
        PROBE_TIMEOUTS.labels(phase=phase).inc()


def observe_pfsense_preflight_duration(
    *,
    outcome: str,
    duration_seconds: float,
) -> None:
    """Record bounded pfSense preflight latency without dynamic labels."""
    if outcome not in _PFSENSE_PREFLIGHT_OUTCOMES:
        return
    if not math.isfinite(duration_seconds) or duration_seconds < 0:
        return
    PFSENSE_PREFLIGHT_DURATION.labels(outcome=outcome).observe(duration_seconds)


def record_pfsense_protective_skip(reason: str) -> None:
    """Count only the fixed protection reasons implemented by the observer."""
    if reason in _PFSENSE_PROTECTIVE_SKIP_REASONS:
        PFSENSE_PROTECTIVE_SKIPS.labels(reason=reason).inc()


def pfsense_api_request_started(phase: str) -> None:
    """Record one actually-started pfSense API request with bounded labels."""
    if phase in _PFSENSE_REQUEST_PHASES:
        PFSENSE_API_REQUESTS.labels(phase=phase).inc()
        PFSENSE_API_REQUESTS_IN_FLIGHT.labels(phase=phase).inc()


def pfsense_api_request_finished(phase: str) -> None:
    """Balance the in-flight gauge for one bounded pfSense request phase."""
    if phase in _PFSENSE_REQUEST_PHASES:
        PFSENSE_API_REQUESTS_IN_FLIGHT.labels(phase=phase).dec()


def probe_started() -> None:
    """Increment active request-budgeted probes."""
    PROBES_IN_FLIGHT.inc()


def probe_finished() -> None:
    """Decrement active request-budgeted probes."""
    PROBES_IN_FLIGHT.dec()
