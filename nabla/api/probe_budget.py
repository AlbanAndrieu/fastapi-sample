"""Per-request concurrency and deadline budgets for diagnostic probes."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
import math
import time
from typing import TypeVar

from nabla.api.probe_metrics import (
    probe_finished,
    probe_started,
    record_probe_timeout,
)

T = TypeVar("T")


def _now() -> float:
    return time.monotonic()


@dataclass(slots=True)
class ProbeBudget:
    """Bound active probe fan-out and the total wall-clock diagnostic budget.

    Budgets are intentionally request-scoped. This avoids process-global asyncio
    primitives becoming bound to a different event loop while still ensuring a
    single health request cannot create unbounded origin work.
    """

    deadline_seconds: float
    max_concurrency: int
    _started_at: float = field(init=False, repr=False)
    _semaphore: asyncio.Semaphore = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not math.isfinite(self.deadline_seconds) or self.deadline_seconds <= 0:
            raise ValueError("deadline_seconds must be a finite positive value")
        if self.max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        self._started_at = _now()
        self._semaphore = asyncio.Semaphore(self.max_concurrency)

    def remaining_seconds(self) -> float:
        """Return the remaining aggregate budget without going negative."""
        return max(0.0, self.deadline_seconds - (_now() - self._started_at))

    async def run(
        self,
        factory: Callable[[], Awaitable[T]],
        *,
        timeout_value: Callable[[], T],
    ) -> T:
        """Run one lazy probe under the shared concurrency/deadline budget.

        A factory is used instead of a pre-created coroutine so probes that expire
        while queued are never started. Cancellation from the caller is preserved.
        """
        remaining = self.remaining_seconds()
        if remaining <= 0:
            record_probe_timeout("deadline")
            return timeout_value()

        acquired = False
        try:
            try:
                async with asyncio.timeout(remaining):
                    await self._semaphore.acquire()
                acquired = True
            except TimeoutError:
                record_probe_timeout("queue")
                return timeout_value()

            remaining = self.remaining_seconds()
            if remaining <= 0:
                record_probe_timeout("deadline")
                return timeout_value()

            probe_started()
            try:
                try:
                    async with asyncio.timeout(remaining):
                        return await factory()
                except TimeoutError:
                    record_probe_timeout("origin")
                    return timeout_value()
            finally:
                probe_finished()
        finally:
            if acquired:
                self._semaphore.release()
