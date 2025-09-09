"""Test the API."""

from typing import Dict

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from serve import app

# from unittest.mock import patch


@pytest.fixture(scope="module")
def test_app():
    client = TestClient(app)
    yield client  # testing happens here


def test_pong_v1(*args) -> None:
    """It runs and gives correct response from pong."""

    client = TestClient(app)
    expected_status: int = 200
    expected_response: Dict[str, str] = {"ping": "pong v1!"}

    # when
    response = client.get("/v1/pong")

    # then
    assert response.status_code == expected_status
    assert response.json() == expected_response


def test_ping_v1(*args) -> None:
    """It runs and gives correct response from ping."""

    client = TestClient(app)
    expected_status: int = 200

    # QUOTES = [
    # "Strive not to be a success, but rather to be of value. - Albert Einstein",
    # "Believe you can and you're halfway there. - Theodore Roosevelt",
    # "The future belongs to those who believe in the beauty of their dreams. - Eleanor Roosevelt",
    # ]

    # when
    response = client.get("/v1/ping")

    # then
    assert response.status_code == expected_status
    assert response.json() is not None


def test_ping_v2(*args) -> None:
    """It runs and gives correct response from ping."""

    client = TestClient(app)
    expected_status: int = 200

    # when
    response = client.get("/v2/ping")

    # then
    assert response.status_code == expected_status
    assert response.json() == {"ping": "pong v2!"}


def test_message_hello_world_v1(*args) -> None:
    """It runs and gives Hello World."""

    client = TestClient(app)
    expected_status: int = 200

    # when
    response = client.get("/v1/message")

    # then
    assert response.status_code == expected_status
    assert response.json() == {"Hello": "World"}


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


def test_exception(*args) -> None:
    """It runs and gives exception."""

    client = TestClient(app)
    expected_status: int = 500

    # when
    response = client.get("/test/exception")

    # then
    assert response.status_code == expected_status
    assert response.json() == {"detail": "Got sadness"}


def test_env(*args) -> None:
    """It runs and gives env"""

    client = TestClient(app)
    expected_status: int = 500

    response = client.get("/test/env")

    assert response.status_code == expected_status
    assert response.json() == {
        "detail": "Env not available outside of Cloudflare worker",
    }


def test_invalid(*args) -> None:
    """It runs and gives error"""

    client = TestClient(app)

    # with pytest.raises(ValueError) as exc_info:
    # with pytest.raises(TypeError("Invalid")):
    with pytest.raises(HTTPException):
        client.get("/test/invalid")
        # response = client.get("/test/invalid")
        # assert response.json() == {
        #     "detail": "Invalid",
        # }
        # assert exc_info.type is AssertionError

# def test_chain(*args) -> None:
#     """It runs and chain io_task and cpu_task."""

#     client = TestClient(app)
#     expected_status: int = 200

#     # when
#     response = client.get("/chain")

#     # then
#     assert response.status_code == expected_status
#     assert response.json() == {"path": "/chain"}
