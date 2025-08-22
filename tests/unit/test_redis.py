import random

from fastapi.testclient import TestClient

import nabla.api.v1 as v1
from serve import app


def test_new_string_secret():
    secret = v1.string_secret()
    assert len(secret) == v1.SIZE
    assert len(set(secret)) == v1.SIZE
    # assert set(secret).issubset(list(range(1, 27)))
    assert set(secret).issubset(v1.POOL)


def test_fixed_string_secret():
    random.seed(42)
    secret = v1.string_secret()
    # print(secret)
    assert secret == [6, 1, 5, 3]


def test_uniform_secret():
    random.seed(42)
    secret = v1.uniform_secret()
    print(type(secret))
    # print(secret)
    # assert set(secret).issubset(range(0, 3))
    assert isinstance(secret, float)


def test_redis_random_v1(*args) -> None:
    """It runs and gives random number."""

    client = TestClient(app)
    expected_status: int = 200

    # when
    response = client.get("/v1/random")

    print(response.json())
    assert response.status_code == expected_status
    # assert response.json() ==


def test_redis_demo_items_one_second(*args) -> None:
    """It runs and gives the number 1."""

    client = TestClient(app)
    expected_status: int = 200

    # when
    response = client.get("/demo/items/1")

    print(response.json())
    assert response.status_code == expected_status
    assert response.json() == {"item_id": 1, "q": "No Query"}
