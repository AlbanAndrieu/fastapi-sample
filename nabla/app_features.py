"""Explicit subsystem switches for the FastAPI application factory.

This module is intentionally dependency-free so lifecycle code, the factory and
tests can share the same feature contract without importing heavy integrations.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any

SUBSYSTEM_ENABLED = "enabled"
SUBSYSTEM_DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class AppFeatures:
    """Subsystems wired into one application instance.

    The defaults describe the production application: every subsystem is
    enabled. Enabled PostgreSQL/Redis are still optional at runtime unless
    ``POSTGRES_REQUIRED``/``REDIS_REQUIRED`` are set (see ``nabla.lifespan``).

    - ``database``: PostgreSQL startup, schema init and DB-backed routes.
    - ``redis``: Redis client lifecycle, event listener and topology heartbeat.
    - ``observability``: Datadog, Pyroscope, Prometheus, OTLP, Logfire, Sentry.
    - ``mcp``: MCP Streamable HTTP server, A2A, MCP ops routes and MCP clients.
    - ``rag``: AI/RAG workflow routes (deep agents with OpenRAG MCP tools).
    """

    database: bool = True
    redis: bool = True
    observability: bool = True
    mcp: bool = True
    rag: bool = True

    @classmethod
    def minimal(cls) -> AppFeatures:
        """Return a local diagnostics profile without external side effects."""
        return cls(
            database=False,
            redis=False,
            observability=False,
            mcp=False,
            rag=False,
        )

    def subsystem_states(self) -> dict[str, str]:
        """Return the explicit ``enabled``/``disabled`` state of every subsystem."""
        return {field.name: SUBSYSTEM_ENABLED if getattr(self, field.name) else SUBSYSTEM_DISABLED for field in fields(self)}


def features_from_state(state: Any) -> AppFeatures:
    """Return the features attached by the factory, or the production defaults."""
    features = getattr(state, "features", None)
    return features if isinstance(features, AppFeatures) else AppFeatures()


def disabled_subsystem_check(subsystem: str) -> dict[str, Any]:
    """Describe a dependency check intentionally not performed for a disabled subsystem."""
    return {
        "reachable": None,
        "skipped": True,
        "state": SUBSYSTEM_DISABLED,
        "reason": f"{subsystem} subsystem disabled by application features",
    }
