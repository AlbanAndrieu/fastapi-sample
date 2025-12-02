
import pytest
from fastapi.testclient import TestClient

from server import app
from tests.unit.conftest import requires_env


@pytest.fixture(scope="module")
def test_app():
    client = TestClient(app)
    yield client  # testing happens here


@requires_env("DEV", "UAT")
def test_admin_panel(test_app):
    response = test_app.post(
        "/admin",
        data={
            "username": "testuser1",
            "password": "qwerty@123",
        },
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


@requires_env("DEV", "UAT")
def test_admin_user_not_found(test_app):
    response = test_app.post(
        "/admin/users/list",
        data={
            "username": "johndoe",
            "password": "qwerty@123",
        },
    )
    assert response.status_code == 200
    assert response.json()["access_token"]

