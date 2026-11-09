"""Minimal on-demand process resource evidence for an authenticated operator.

This does not estimate the FastAPI Cloud bill or replica count. The provider's
Metrics screen remains authoritative for limits and aggregate vCPU/memory.
No background sampling, network access or raw process environment is involved.
"""

from __future__ import annotations

from datetime import UTC, datetime

import psutil


def snapshot_process_resources() -> dict[str, object]:
    """Read local RSS and cumulative CPU time in one low-cost psutil pass."""
    process = psutil.Process()
    with process.oneshot():
        rss = int(process.memory_info().rss)
        cpu = process.cpu_times()
        threads = int(process.num_threads())
    return {
        "schema_version": 1,
        "model": "process-resource-observation",
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "rss_bytes": max(0, rss),
        "process_cpu_seconds_total": round(
            max(0.0, float(cpu.user) + float(cpu.system)), 4
        ),
        "threads": max(0, threads),
        "sample_type": "single_observation",
        "cpu_utilization_percent": None,
        "replica_count": None,
        "billing_usage": None,
    }
