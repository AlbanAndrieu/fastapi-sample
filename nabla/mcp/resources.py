"""Read-only FastMCP resources for safe operational discovery."""

from __future__ import annotations

import json

from fastmcp import FastMCP

_OPERATIONS = (
    {
        "id": "runtime-metadata",
        "endpoint": "/v1/runtime/metadata",
        "access": "runtime diagnostics opt-in",
    },
    {
        "id": "homelab-status",
        "endpoint": "/api/homelab/status",
        "access": "public sanitized runtime status",
    },
    {
        "id": "homelab-runtime",
        "endpoint": "/api/homelab/runtime",
        "access": "public sanitized TrueNAS runtime",
    },
    {
        "id": "runtime-topology",
        "endpoint": "/api/runtime/topology",
        "access": "public sanitized topology",
    },
    {
        "id": "detailed-diagnostics",
        "endpoint": "/api/homelab/health",
        "access": "DIAGNOSTICS_ACCESS_KEY when configured; metadata only in MCP resource",
    },
)


def register_fastapi_resources(server: FastMCP) -> None:
    """Register safe discovery resources without duplicating protected diagnostics."""

    @server.resource(
        "resource://fastapi/operations",
        name="FastAPI Operations",
        description="Read-only discovery metadata for runtime and homelab operations.",
        mime_type="application/json",
        annotations={"readOnlyHint": True, "idempotentHint": True},
    )
    def operations_index() -> str:
        return json.dumps(
            {
                "service": "fastapi-sample",
                "mcp_endpoint": "/mcp",
                "operations": _OPERATIONS,
            },
            sort_keys=True,
        )
