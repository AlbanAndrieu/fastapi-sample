import os

import pytest
from starlette.testclient import TestClient

# Unit tests import ``server_app`` at collection time. Keep that import hermetic by
# providing the same non-secret defaults as the Python CI workflow.
os.environ.setdefault("KEYCLOAK_SERVER_URL", "http://localhost:8080")
os.environ.setdefault("KEYCLOAK_REALM", "test")
os.environ.setdefault("KEYCLOAK_CLIENT_ID", "test")
os.environ.setdefault("KEYCLOAK_CLIENT_SECRET", "test-secret")
os.environ.setdefault("OAUTH_TOKEN_SECRET", "mocked-oauth-token-secret")

# Never let a developer's shell/runtime telemetry configuration leak into unit
# tests. Tests that exercise telemetry configuration can still monkeypatch these
# variables explicitly after collection.
for key in (
    "METRICS_ENABLED",
    "LOGFIRE_ENABLED",
    "SENTRY_ENABLED",
    "DATADOG_ENABLED",
    "UNLEASH_ENABLED",
    "STATSIG_ENABLED",
    "DD_TRACE_ENABLED",
    "DD_PROFILING_ENABLED",
):
    os.environ[key] = "false"
os.environ["LOGFIRE_TOKEN"] = ""
os.environ["SENTRY_DSN"] = ""
os.environ["SENTRY_LOCAL_DSN"] = ""
os.environ["UNLEASH_INSTANCE_ID"] = ""
os.environ["STATSIG_API_KEY"] = ""

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
