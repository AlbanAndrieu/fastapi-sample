"""Shared value types for the external probe cache."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ProbeCachePolicy:
    """Fresh/failure/stale windows for one external probe."""

    success_ttl: float
    failure_ttl: float
    stale_ttl: float
    lock_ttl: int = 15
    wait_timeout: float = 0.6
    poll_interval: float = 0.1


@dataclass(frozen=True, slots=True)
class ProbeCacheResult:
    """Current cached/origin value plus optional last-known-good evidence."""

    value: dict[str, Any]
    metadata: dict[str, Any]
    last_good: dict[str, Any] | None = None
