import os
from collections.abc import Iterator

import pytest
from starlette.testclient import TestClient


@pytest.fixture(scope="module")
def test_app() -> Iterator[TestClient]:
    """Create the full application only for tests that explicitly request it."""
    from server_app import app  # noqa: PLC0415 - keep full-app side effects scoped to this fixture

    with TestClient(app) as client:
        yield client


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
