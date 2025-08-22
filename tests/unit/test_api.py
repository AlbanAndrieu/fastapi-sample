"""Test the API."""

from typing import Dict

import pytest
from fastapi.testclient import TestClient

from serve import app

# from unittest.mock import patch


@pytest.fixture(scope="module")
def test_app():
    client = TestClient(app)
    yield client  # testing happens here


def test_pong(*args) -> None:
    """It runs and gives correct response from pong."""

    client = TestClient(app)
    expected_status: int = 200
    expected_response: Dict[str, str] = {"ping": "pong v1!"}

    # when
    response = client.get("/v1/pong")

    # then
    assert response.status_code == expected_status
    assert response.json() == expected_response


def test_ping(*args) -> None:
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
