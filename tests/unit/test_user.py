"""Test the API."""

import pytest
from fastapi.testclient import TestClient

from server import app


@pytest.fixture(scope="module")
def test_app():
    client = TestClient(app)
    yield client  # testing happens here


def test_users(*args) -> None:
    """It runs and gives correct response for users."""

    client = TestClient(app)
    expected_status: int = 200

    # with pytest.raises(AssertionError):
    response = client.get("/test/users/0")

    # then
    assert response.status_code == expected_status
    assert response.json() == {
        "name": "User 0",
        "email": "alban.andrieu@free.fr",
        "password": "XXX",
    }


def test_user_me(*args) -> None:
    """It runs and gives correct response for user me."""

    client = TestClient(app)
    expected_status: int = 404

    response = client.get("https://jusmundi.com/api/user/me")

    assert response.status_code == expected_status
    # assert response.json() == {
    #     "name": "User 0",
    #     "email": "alban.andrieu@free.fr",
    # }
