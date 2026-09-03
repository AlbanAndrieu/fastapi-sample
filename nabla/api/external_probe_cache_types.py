"""Shared value types for the external probe cache."""

from __future__ import annotations

from dataclasses import dataclass
import math
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

    def __post_init__(self) -> None:
        for field_name in ("success_ttl", "failure_ttl", "stale_ttl", "wait_timeout"):
            value = float(getattr(self, field_name))
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{field_name} must be a finite non-negative value")
        if self.lock_ttl < 1:
            raise ValueError("lock_ttl must be at least 1 second")
        if not math.isfinite(self.poll_interval) or self.poll_interval <= 0:
            raise ValueError("poll_interval must be a finite positive value")
        if self.wait_timeout > 0 and self.poll_interval > self.wait_timeout:
            raise ValueError("poll_interval must not exceed a positive wait_timeout")


@dataclass(frozen=True, slots=True)
class ProbeCacheResult:
    """Current cached/origin value plus optional last-known-good evidence."""

    value: dict[str, Any]
    metadata: dict[str, Any]
    last_good: dict[str, Any] | None = None
