"""In-memory, task-local phase evidence for timed-out homelab probes.

Records only bounded phase names and monotonic elapsed milliseconds; never
records targets, headers, DNS answers, authentication or exception text.
Weak task keys ensure a cancelled task cannot pin retained diagnostic state.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Literal
from weakref import WeakKeyDictionary

from nabla.api.health_probe_utils import elapsed_ms

ProbePhase = Literal[
    "waiting_on_semaphore",
    "dns_in_progress",
    "head_get_in_progress",
    "access_secondary_in_progress",
    "tcp_in_progress",
]
DEADLINE_PHASES = (
    "not_started",
    "waiting_on_semaphore",
    "dns_in_progress",
    "head_get_in_progress",
    "access_secondary_in_progress",
    "tcp_in_progress",
)

# Only the current async worker's probe tasks are tracked. The values are
# primitive timing observations, not service objects or request metadata.
_PHASE_BY_TASK: WeakKeyDictionary[asyncio.Task[Any], tuple[ProbePhase, float]] = (
    WeakKeyDictionary()
)


def mark_probe_phase(phase: ProbePhase) -> None:
    """Record a safe phase transition in the currently running probe task."""
    if phase not in DEADLINE_PHASES[1:]:
        raise ValueError("unrecognized probe phase")
    task = asyncio.current_task()
    if task is not None:
        _PHASE_BY_TASK[task] = (phase, time.perf_counter())


def snapshot_probe_phase(task: asyncio.Task[Any]) -> dict[str, str | int | None]:
    """Take a bounded copy before cancelling a task at the global deadline."""
    observation = _PHASE_BY_TASK.get(task)
    if observation is None:
        return {"deadline_phase": "not_started", "deadline_phase_elapsed_ms": None}
    phase, started = observation
    return {
        "deadline_phase": phase,
        "deadline_phase_elapsed_ms": min(60_000, elapsed_ms(started)),
    }


def clear_probe_phase(task: asyncio.Task[Any]) -> None:
    """Discard short-lived state after the enclosing bounded batch completes."""
    _PHASE_BY_TASK.pop(task, None)
