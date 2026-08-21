import os

import pytest
from starlette.testclient import TestClient

from server_app import app


@pytest.fixture(scope="module")
def test_app():
    client = TestClient(app)
    yield client  # testing happens here


# Because some tests are only suitable for certain environments, like having access to keycloak for test_login.py
def requires_env(*envs):
    env = os.environ.get(
        "ENV",
        "local",
    )

    return pytest.mark.skipif(
        env not in list(envs),
        reason=f"Not suitable environment {env} for current test",
    )
