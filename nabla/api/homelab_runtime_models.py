"""Sanitized TrueNAS runtime models and raw app normalization."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ObservedContainer(BaseModel):
    """One container reported by TrueNAS active_workloads."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    service_name: str | None = None
    image: str | None = None
    state: str | None = None


class ObservedApp(BaseModel):
    """One installed TrueNAS App with runtime facts used for reconciliation."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    app_id: str
    name: str
    state: str = "UNKNOWN"
    version: str | None = None
    human_version: str | None = None
    upgrade_available: bool = False
    containers: list[ObservedContainer] = Field(default_factory=list)


class TrueNASRuntimeSnapshot(BaseModel):
    """Read-only sanitized snapshot returned to homelab consumers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["truenas"] = "truenas"
    observed_at: str
    configured: bool
    reachable: bool
    stale: bool = False
    apps: list[ObservedApp] = Field(default_factory=list)
    error: str | None = None


def observed_app(raw: dict[str, Any]) -> ObservedApp:
    """Normalize the subset of TrueNAS app.query used by reconciliation."""
    workloads = raw.get("active_workloads") or {}
    raw_containers = workloads.get("container_details") or []
    containers = [
        ObservedContainer(
            service_name=(str(container.get("service_name")) if container.get("service_name") is not None else None),
            image=(str(container.get("image")) if container.get("image") is not None else None),
            state=(str(container.get("state")) if container.get("state") is not None else None),
        )
        for container in raw_containers
        if isinstance(container, dict)
    ]
    app_id = str(raw.get("id") or raw.get("name") or "unknown")
    return ObservedApp(
        app_id=app_id,
        name=str(raw.get("name") or app_id),
        state=str(raw.get("state") or raw.get("status") or "UNKNOWN"),
        version=(str(raw["version"]) if raw.get("version") is not None else None),
        human_version=(str(raw["human_version"]) if raw.get("human_version") is not None else None),
        upgrade_available=bool(raw.get("upgrade_available", False)),
        containers=containers,
    )
