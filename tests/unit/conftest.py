import os
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

# Required non-secret settings defaults live in tests/conftest.py.

# Operational access keys are deployment secrets. A developer's configured
# diagnostics/admin key must not turn ordinary unit-test requests into 401s.
# Access-control behavior is covered explicitly in test_access_control.py.
for key in (
    "DIAGNOSTICS_ACCESS_KEY",
    "ADMIN_ACCESS_KEY",
):
    os.environ.pop(key, None)

import nabla.lifespan as lifecycle  # noqa: E402
from nabla import access_control  # noqa: E402
from nabla.api.notes import models as note_models  # noqa: E402
from nabla.api.users import models as user_models  # noqa: E402
from server_app import app  # noqa: E402


def _patch_database_startup(stack: ExitStack) -> None:
    """Keep the application lifespan hermetic: no PostgreSQL connection or DDL.

    Route tests mock their CRUD layer; startup connection/schema behavior is
    covered explicitly in test_lifespan.py.
    """
    database = SimpleNamespace(connect=AsyncMock(), disconnect=AsyncMock())
    stack.enter_context(patch.object(lifecycle, "database", database))
    stack.enter_context(patch.object(lifecycle, "init_db", AsyncMock()))
    stack.enter_context(patch.object(lifecycle, "init_db_sensor_reading", AsyncMock()))
    stack.enter_context(patch.object(note_models, "init_db", AsyncMock()))
    stack.enter_context(patch.object(user_models, "init_db", AsyncMock()))


@pytest.fixture(scope="module")
def test_app():
    """Shared unit-test client with operational access protection disabled."""
    settings = SimpleNamespace(
        admin_access_key=None,
        diagnostics_access_key=None,
    )
    with ExitStack() as stack:
        stack.enter_context(patch.object(access_control, "get_settings", return_value=settings))
        _patch_database_startup(stack)
        client = stack.enter_context(TestClient(app))
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
