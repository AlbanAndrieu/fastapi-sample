import os

import pytest
from starlette.testclient import TestClient

# Unit tests import ``server_app`` at collection time. Keep that import hermetic by
# providing the same non-secret defaults as the Python CI workflow while preserving
# any explicit environment supplied by a test or runner.
os.environ.setdefault("KEYCLOAK_SERVER_URL", "http://localhost:8080")
os.environ.setdefault("KEYCLOAK_REALM", "test")
os.environ.setdefault("KEYCLOAK_CLIENT_ID", "test")
os.environ.setdefault("KEYCLOAK_CLIENT_SECRET", "test-secret")
os.environ.setdefault("OAUTH_TOKEN_SECRET", "mocked-oauth-token-secret")
os.environ.setdefault("METRICS_ENABLED", "false")
os.environ.setdefault("LOGFIRE_ENABLED", "false")
os.environ.setdefault("SENTRY_ENABLED", "false")
os.environ.setdefault("DATADOG_ENABLED", "false")
os.environ.setdefault("UNLEASH_ENABLED", "false")
os.environ.setdefault("STATSIG_ENABLED", "false")

from server_app import app  # noqa: E402


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
