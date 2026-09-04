"""Fixed-cardinality Prometheus metrics for external diagnostic probes."""

from __future__ import annotations

from prometheus_client import Counter, Gauge

_PROVIDERS = frozenset({"truenas", "pfsense", "cloudflare"})
_PROVIDER_OUTCOMES = frozenset({"success", "failure", "suppressed"})
_CIRCUIT_STATES = ("closed", "open", "half_open")
_CACHE_OUTCOMES = frozenset(
    {"l1_hit", "redis_hit", "local_hit", "miss", "stale", "redis_degraded"}
)
_TIMEOUT_PHASES = frozenset({"deadline", "queue", "origin"})

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


def record_provider_outcome(provider: str | None, outcome: str) -> None:
    """Record only pre-approved provider/outcome label values."""
    if provider in _PROVIDERS and outcome in _PROVIDER_OUTCOMES:
        PROVIDER_OUTCOMES.labels(provider=provider, outcome=outcome).inc()


def record_provider_budget_rejection(provider: str | None) -> None:
    """Record only bounded provider labels for rate-budget suppression."""
    if provider in _PROVIDERS:
        PROVIDER_BUDGET_REJECTIONS.labels(provider=provider).inc()


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


def probe_started() -> None:
    """Increment active request-budgeted probes."""
    PROBES_IN_FLIGHT.inc()


def probe_finished() -> None:
    """Decrement active request-budgeted probes."""
    PROBES_IN_FLIGHT.dec()
