"""Explicit subsystem switches for the FastAPI application factory.

This module is intentionally dependency-free so lifecycle code, the factory and
tests can share the same feature contract without importing heavy integrations.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AppFeatures:
    """Subsystems wired into one application instance.

    The defaults describe the production application: every subsystem is
    enabled and PostgreSQL remains a critical startup dependency.

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
