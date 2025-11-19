"""Test the API."""

from typing import Dict

import pytest
from fastapi.testclient import TestClient

from server import app

# from unittest.mock import patch


@pytest.fixture(scope="module")
def test_app():
    client = TestClient(app)
    yield client  # testing happens here


def test_pong_v1(test_app) -> None:
    """It runs and gives correct response from pong."""

    expected_status: int = 200
    expected_response: Dict[str, str] = {"ping": "pong v1!"}

    # when
    response = test_app.get("/v1/pong")

    # then
    assert response.status_code == expected_status
    assert response.json() == expected_response


def test_ping_v1(test_app) -> None:
    """It runs and gives correct response from ping."""

    expected_status: int = 200

    # QUOTES = [
    # "Strive not to be a success, but rather to be of value. - Albert Einstein",
    # "Believe you can and you're halfway there. - Theodore Roosevelt",
    # "The future belongs to those who believe in the beauty of their dreams. - Eleanor Roosevelt",
    # ]

    # when
    response = test_app.get("/v1/ping")

    # then
    assert response.status_code == expected_status
    assert response.json() is not None


def test_ping_v2(test_app) -> None:
    """It runs and gives correct response from ping."""

    expected_status: int = 200

    # when
    response = test_app.get("/v2/ping")

    # then
    assert response.status_code == expected_status
    assert response.json() == {"ping": "pong v2!"}


def test_message_hello_world_v1(test_app) -> None:
    """It runs and gives Hello World."""

    expected_status: int = 200

    # when
    response = test_app.get("/v1/message")

    # then
    assert response.status_code == expected_status
    assert response.json() == {"Hello": "World"}


def test_exception(test_app) -> None:
    """It runs and gives exception."""

    expected_status: int = 500

    # when
    response = test_app.get("/test/exception")

    # then
    assert response.status_code == expected_status
    assert response.json() == {"detail": "Got sadness"}


def test_env(test_app) -> None:
    """It runs and gives env"""

    expected_status: int = 500

    response = test_app.get("/test/env")

    assert response.status_code == expected_status
    assert response.json() == {
        "detail": "Env not available outside of Cloudflare worker",
    }


def test_invalid(test_app) -> None:
    """It runs and gives error"""

    expected_status: int = 500

    # with pytest.raises(TypeError("Invalid")):
    response = test_app.get("/test/invalid")
    assert response.status_code == expected_status
    assert response.json() == {
        "detail": "Invalid request",
    }


def test_health(test_app) -> None:
    """It runs and gives health status."""

    expected_status: int = 200

    # when
    response = test_app.get("/health")

    # then
    assert response.status_code == expected_status
    status = response.json()
    assert status["status"] == "healthy"
    assert status["readings_count"] == 50
    assert status["active_connections"] == 0
    assert status["total_requests"] == 2


@pytest.mark.skip(reason="Skipping this test for now")
def test_chain(test_app) -> None:
    """It runs and chain io_task and cpu_task."""

    expected_status: int = 200

    # when
    response = test_app.get("/chain")

    # then
    assert response.status_code == expected_status
    assert response.json() == {"path": "/chain"}
