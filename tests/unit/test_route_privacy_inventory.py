"""Offline, no-app-start privacy route inventory checks."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from fastapi import FastAPI
from starlette.routing import Host, Mount, Route, WebSocketRoute

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/audit/inventory_fastapi_routes.py"
spec = importlib.util.spec_from_file_location("inventory_fastapi_routes", SCRIPT)
assert spec is not None and spec.loader is not None
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)


def _empty(_request):
    return None


def test_sensitive_routes_are_not_public_by_default() -> None:
    app = FastAPI(docs_url=None, openapi_url=None)
    app.add_api_route("/api/homelab/health", _empty, methods=["GET"])
    app.add_api_route("/api/health-board", _empty, methods=["GET"])
    app.add_api_route("/private/ops/api/v1/services", _empty, methods=["GET"])
    app.add_api_route("/api/public-topology", _empty, methods=["GET"])
    app.add_api_route("/api/public-homelab/v1", _empty, methods=["GET"])
    app.add_api_route("/api/unknown", _empty, methods=["POST"])
    routes = {row["path"]: row for row in inventory.inventory_routes(app.routes)}
    assert routes["/api/homelab/health"]["intended_policy"] == "OWNER"
    assert routes["/api/health-board"]["intended_policy"] == "OWNER"
    assert routes["/private/ops/api/v1/services"]["intended_policy"] == "OWNER"
    assert routes["/api/public-topology"]["intended_policy"] == "OWNER"
    assert routes["/api/public-homelab/v1"]["intended_policy"] == "PUBLIC_CANDIDATE"
    assert routes["/api/unknown"]["intended_policy"] == "REVIEW"
    assert inventory.audit_summary(list(routes.values()))["review_required"] == 1


def test_prefix_boundaries_and_non_get_public_candidates() -> None:
    assert inventory.intended_policy("/metrics", ["GET"], "http") == "INTERNAL"
    assert inventory.intended_policy("/metrics-preview", ["GET"], "http") == "REVIEW"
    assert inventory.intended_policy("/api/homelab-topology", ["GET"], "http") == "OWNER"
    assert inventory.intended_policy("/api/runtime/topology", ["GET"], "http") == "OWNER"
    assert inventory.intended_policy("/api/runtime/topology-extra", ["GET"], "http") == "REVIEW"
    assert inventory.intended_policy("/api/homelabish", ["GET"], "http") == "REVIEW"
    assert inventory.intended_policy("/api/public-homelab/v1", ["POST"], "http") == "REVIEW"
    assert inventory.intended_policy("/health", ["DELETE"], "http") == "REVIEW"
    assert inventory.intended_policy("/health", [], "http") == "REVIEW"
    assert inventory.intended_policy("/openapi.json", ["GET"], "http") == "REVIEW"


def test_mounts_and_websocket_are_included() -> None:
    async def websocket(_socket):
        return None

    routes = [
        Mount("/private/ops", routes=[Route("/overview", _empty, methods=["GET"])]),
        WebSocketRoute("/ws/sensor", websocket),
        Mount("/opaque", app=_empty),
        Host("app.example.invalid", app=_empty),
    ]
    output = inventory.inventory_routes(routes)
    by_path = {row["path"]: row for row in output}
    assert by_path["/private/ops/overview"]["intended_policy"] == "OWNER"
    assert by_path["/ws/sensor"]["kind"] == "websocket"
    assert by_path["/ws/sensor"]["intended_policy"] == "INTERNAL"
    assert by_path["/opaque"]["kind"] == "opaque_mount"
    assert by_path["/opaque"]["intended_policy"] == "REVIEW"
    assert inventory.intended_policy("/mcp", [], "opaque_mount") == "REVIEW"
    assert by_path["/__host_mount__"]["intended_policy"] == "REVIEW"
    assert output == sorted(output, key=lambda row: (row["path"], row["kind"], str(row["methods"])))
