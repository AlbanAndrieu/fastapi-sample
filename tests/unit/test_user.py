"""Test the API."""

import pytest
from fastapi.testclient import TestClient

from server_app import app


@pytest.fixture(scope="module")
def test_app():
    client = TestClient(app)
    yield client  # testing happens here


def test_user_current(test_app) -> None:
    """It runs and gives correct response for users."""

    expected_status: int = 200

    # with pytest.raises(AssertionError):
    response = test_app.get("/test/users/current")

    # then
    print(response.json())
    assert response.status_code == expected_status
    result = response.json()
    assert result["name"] == "Alban Andrieu"
    assert "password" not in result
    assert result["phone"] == "+33 (0) 6 95 43 53 53"
    assert result["address"] == "11 terrasse de l'université"
    assert result["city"] == "Paris"
    assert result["state"] == "FR"
    assert result["zipcode"] == "92000"
    assert result["country"] == "France"
    assert result["email"].startswith("alban.andrieu@")


def test_users(test_app) -> None:
    """It runs and gives correct response for users."""

    expected_status: int = 422

    # with pytest.raises(AssertionError):
    response = test_app.get("/test/users/0")

    # then
    assert response.status_code == expected_status
    assert response.json() == {"detail": [{"type": "missing", "loc": ["query", "current_user"], "msg": "Field required", "input": None}]}


def test_user_me(test_app) -> None:
    """It runs and gives correct response for user me."""

    expected_status: int = 404

    response = test_app.get("https://fastapi-sample.fastapicloud.dev/api/user/me")

    assert response.status_code == expected_status
    # assert response.json() == {
    #     "name": "User 0",
    #     "email": "alban.andrieu@gmail.com",
    # }
