import asyncio
import random

import pytest
from fastapi.testclient import TestClient

import nabla.api.demo.demo as demo
from server import app


@pytest.fixture(scope="module")
def test_app():
    client = TestClient(app)
    yield client  # testing happens here

@pytest.fixture(scope="session")
def event_loop(request):
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

def test_new_string_secret():
    secret = demo.string_secret()
    assert len(secret) == demo.SIZE
    assert len(set(secret)) == demo.SIZE
    # assert set(secret).issubset(list(range(1, 27)))
    assert set(secret).issubset(demo.POOL)


def test_fixed_string_secret():
    random.seed(42)
    secret = demo.string_secret()
    # print(secret)
    assert secret == [6, 1, 5, 3]


def test_uniform_secret():
    random.seed(42)
    secret = demo.uniform_secret()
    print(type(secret))
    # print(secret)
    # assert set(secret).issubset(range(0, 3))
    assert isinstance(secret, float)
    assert secret == max(1, min(secret, 10))  # Between 1-10 seconds


def test_redis_demo_random(test_app) -> None:
    """It runs and gives random number."""

    expected_status: int = 200

    # when
    response = test_app.get("/demo/random")

    print(response.json())
    assert response.status_code == expected_status

    assert response.json() != "b'1'"
    assert response.json() is not None


async def test_redis_demo_items_one_second(test_app) -> None:
    """It runs and gives the number 1."""

    expected_status: int = 200

    # when
    response = test_app.get("/demo/items/1")

    print(response.json())
    assert response.status_code == expected_status
    assert response.json() == {"item_id": 1, "q": "No Query"}


def test_redis_demo_items_two_second(test_app) -> None:
    """It runs and gives the number 1."""

    expected_status: int = 200

    # when
    response = test_app.get("/demo/items/2")

    print(response.json())
    assert response.status_code == expected_status
    assert response.json() == {"item_id": 2, "q": "No Query"}
