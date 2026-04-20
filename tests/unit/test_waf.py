from fastapi.testclient import TestClient

from server_app import app


def test_removed_demo_feature_flag_routes_are_not_mounted() -> None:
    """Retired demo routes behind stale flags should no longer be served."""
    with TestClient(app) as test_client:
        response_dispatch = test_client.get("/demo/dispatch/customer/123")
        response_health = test_client.get("/demo/dev/heatlh")
        response_internal = test_client.get("/demo/internal-api/")

    assert response_dispatch.status_code == 404
    assert response_health.status_code == 404
    assert response_internal.status_code == 404
