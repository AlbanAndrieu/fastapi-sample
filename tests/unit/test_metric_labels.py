"""Bounded-cardinality Prometheus route labels."""

from fastapi import FastAPI, Request
from starlette.routing import Match

from nabla.middleware import metric_route_label


def _request(app: FastAPI, path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
            "query_string": b"",
            "app": app,
        }
    )


def test_metric_route_label_uses_stable_path_template() -> None:
    app = FastAPI()

    @app.get("/users/{user_id}")
    def get_user(user_id: str) -> dict[str, str]:
        return {"user_id": user_id}

    assert metric_route_label(_request(app, "/users/12345")) == "/users/{user_id}"


def test_metric_route_label_groups_unknown_paths() -> None:
    assert metric_route_label(_request(FastAPI(), "/random/unique-value")) == "__unmatched__"


class _IncludedRouterWithoutPath:
    """Minimal stand-in for FastAPI's private included-router wrapper."""

    def matches(self, _scope: dict[str, object]) -> tuple[Match, dict[str, object]]:
        return Match.FULL, {}


def test_metric_route_label_handles_route_without_path_attributes() -> None:
    app = FastAPI()
    app.router.routes.insert(0, _IncludedRouterWithoutPath())  # type: ignore[arg-type]

    request = _request(app, "/mcp")
    request.scope["route"] = app.router.routes[0]

    assert metric_route_label(request) == "__unmatched__"
