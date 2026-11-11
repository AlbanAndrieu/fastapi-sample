"""Minimal on-demand process resource evidence for an authenticated operator.

This does not estimate the FastAPI Cloud bill or replica count. The provider's
Metrics screen remains authoritative for limits and aggregate vCPU/memory.
No background sampling, network access or raw process environment is involved.
"""

from __future__ import annotations

from pathlib import Path

import psutil

from nabla.api.platform_health_diagnostics import utc_now



# Fixed Linux cgroup v2 paths. Read only after OWNER authorization; no
# filesystem crawling, no environment inspection and no periodic background job.
_CGROUP_DIR = Path("/sys/fs/cgroup")
_MAX_CGROUP_FILE_BYTES = 4096


def _read_cgroup_file(name: str) -> str | None:
    if name not in {"cpu.max", "cpu.stat", "memory.current", "memory.max", "memory.events"}:
        return None
    try:
        path = _CGROUP_DIR / name
        if not path.is_file() or path.stat().st_size > _MAX_CGROUP_FILE_BYTES:
            return None
        return path.read_text(encoding="ascii")[:_MAX_CGROUP_FILE_BYTES]
    except (OSError, UnicodeError):
        return None


def _nonnegative_integer(raw: str | None) -> int | None:
    if raw is None or not raw.isascii() or not raw.isdecimal() or len(raw) > 20:
        return None
    number = int(raw)
    return number if 0 <= number <= 2**63 - 1 else None


def _cgroup_kv(name: str) -> dict[str, int]:
    raw = _read_cgroup_file(name)
    if raw is None:
        return {}
    values: dict[str, int] = {}
    for line in raw.splitlines()[:32]:
        parts = line.split()
        if len(parts) != 2:
            continue
        value = _nonnegative_integer(parts[1])
        if value is not None and parts[0] in {"usage_usec", "oom", "oom_kill"}:
            values[parts[0]] = value
    return values


def snapshot_cgroup_resources() -> dict[str, object]:
    """Bounded cgroup v2 evidence, with missing values explicitly unknown."""
    current = _nonnegative_integer((_read_cgroup_file("memory.current") or "").strip())
    maximum = _nonnegative_integer((_read_cgroup_file("memory.max") or "").strip())
    quota_text = (_read_cgroup_file("cpu.max") or "").split()
    cpu_limit: float | None = None
    if len(quota_text) == 2:
        quota = _nonnegative_integer(quota_text[0])
        period = _nonnegative_integer(quota_text[1])
        if quota is not None and period and quota > 0:
            cpu_limit = round(quota / period, 4)
    cpu = _cgroup_kv("cpu.stat")
    memory_events = _cgroup_kv("memory.events")
    return {
        "memory_current_bytes": current,
        "memory_limit_bytes": maximum if maximum and maximum > 0 else None,
        "memory_limit_percent": (
            round(100 * current / maximum, 2)
            if current is not None and maximum and maximum > 0 else None
        ),
        "cpu_quota_cores": cpu_limit,
        "cpu_usage_seconds_total": (
            round(cpu["usage_usec"] / 1_000_000, 4)
            if "usage_usec" in cpu else None
        ),
        "oom_kill_count": memory_events.get("oom_kill"),
        "sample_type": "single_observation",
        "source": "linux_cgroup_v2",
    }

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
        "observed_at": utc_now(),
        "rss_bytes": max(0, rss),
        "process_cpu_seconds_total": round(
            max(0.0, float(cpu.user) + float(cpu.system)),
            4,
        ),
        "threads": max(0, threads),
        "sample_type": "single_observation",
        "cpu_utilization_percent": None,
        "replica_count": None,
        "billing_usage": None,
        "cgroup": snapshot_cgroup_resources(),
    }
