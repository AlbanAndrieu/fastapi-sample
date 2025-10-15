import os

import pytest
from starlette.testclient import TestClient

from server import app


@pytest.fixture(scope="module")
def test_app():
    client = TestClient(app)
    yield client  # testing happens here


ACCEPTABLE_FAILURE_RATE = 50


@pytest.hookimpl()
def pytest_sessionfinish(session, exitstatus):
    if exitstatus != pytest.ExitCode.TESTS_FAILED:
        return
    failure_rate = (100.0 * session.testsfailed) / session.testscollected
    if failure_rate <= ACCEPTABLE_FAILURE_RATE:
        session.exitstatus = 0


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
