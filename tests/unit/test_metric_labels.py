"""Bounded-cardinality Prometheus route labels."""

from fastapi import FastAPI, Request

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
