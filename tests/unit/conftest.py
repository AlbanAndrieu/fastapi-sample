import os
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pydantic import SecretStr
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


UNIT_OPS_KEYS = {
    "admin_access_key": ("X-Admin-Key", "unit-admin-key"),
    "diagnostics_access_key": ("X-Diagnostics-Key", "unit-diagnostics-key"),
    "mcp_ops_key": ("X-MCP-Key", "unit-mcp-key"),
}


def unit_ops_settings() -> SimpleNamespace:
    """Fixture-only operational keys: private routes stay fail-closed, not open."""
    return SimpleNamespace(
        ops_route_policy_strict=False,
        **{field: SecretStr(value) for field, (_, value) in UNIT_OPS_KEYS.items()},
    )


def unit_ops_headers() -> dict[str, str]:
    return dict(UNIT_OPS_KEYS.values())


@pytest.fixture
def unit_ops_access(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Authenticate private routes for app instances built by a test itself."""
    monkeypatch.setattr(access_control, "get_settings", unit_ops_settings)
    return unit_ops_headers()


@pytest.fixture(scope="module")
def test_app():
    """Shared unit-test client authenticated with fixture-only operational keys."""
    with ExitStack() as stack:
        stack.enter_context(patch.object(access_control, "get_settings", return_value=unit_ops_settings()))
        _patch_database_startup(stack)
        client = stack.enter_context(TestClient(app, headers=unit_ops_headers()))
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
