# test for the prometheus metrics endpoint

import sys

import pytest
from fastapi.testclient import TestClient

from nabla.main import app

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def test_app():
    client = TestClient(app)
    yield client  # testing happens here
    # teardown
    # database.disconnect()


@pytest.mark.skipif(
    sys.version_info < (3, 8),
    reason="Need Python 3.8 or upper",
)
def test_metrics(test_app):
    response = test_app.get("/metrics")
    assert response.status_code == 200


def test_metrics_get_request(test_app):
    response = test_app.get("/metrics")
    assert response.status_code == 200
    # assert response.headers["content-type"] == "text/plain; version=1.0.0; charset=utf-8'  'text/plain; version=0.0.4; charset=utf-8"
    # Accept modern prometheus_client content-type
    assert response.headers["content-type"].startswith("application/openmetrics-text; version=1.0.0; charset=utf-8")


def test_metrics_inflight_requests_gauge(test_app):
    """fastapi_inflight_requests is exposed for HPA custom metric (scale on in-flight requests)."""
    response = test_app.get("/metrics")
    assert response.status_code == 200
    assert "fastapi_inflight_requests" in response.text


@pytest.mark.skip(reason="Skipping this test for now")
def test_metrics_put_request(test_app):
    response = test_app.put("/metrics")
    assert response.status_code == 405
    assert response.json()["detail"] == "Method Not Allowed"


@pytest.mark.skip(reason="Skipping this test for now")
def test_metrics_invalid_path(test_app):
    response = test_app.get("/metrics/invalid")
    assert response.status_code == 404
    assert response.json()["detail"] == "Not Found"


@pytest.mark.skip(reason="Skipping this test for now")
def test_metrics_invalid_method(test_app):
    response = test_app.post("/metrics")
    assert response.status_code == 405
    assert response.json()["detail"] == "Method Not Allowed"


@pytest.mark.skip(reason="Skipping this test for now")
def test_metrics_post_request(test_app):
    response = test_app.post("/metrics")
    assert response.status_code == 405
    assert response.json()["detail"] == "Method Not Allowed"


@pytest.mark.skip(reason="Skipping this test for now")
def test_metrics_delete_request(test_app):
    response = test_app.delete("/metrics")
    assert response.status_code == 405
    assert response.json()["detail"] == "Method Not Allowed"


@pytest.mark.skip(reason="Skipping this test for now")
def test_metrics_patch_request(test_app):
    response = test_app.patch("/metrics")
    assert response.status_code == 405
    assert response.json()["detail"] == "Method Not Allowed"


@pytest.mark.skip(reason="Skipping this test for now")
def test_metrics_options_request(test_app):
    response = test_app.options("/metrics")
    assert response.status_code == 405
    assert response.json()["detail"] == "Method Not Allowed"
