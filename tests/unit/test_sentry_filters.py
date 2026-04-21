"""Tests for Sentry initialization guards."""

from nabla.utils.sentry_filters import is_pytest_process


def test_is_pytest_process_true_when_pytest_env_present() -> None:
    """Return true when pytest-specific env variable is present."""
    assert is_pytest_process(env={"PYTEST_CURRENT_TEST": "tests/unit/test_api.py::test_health"})


def test_is_pytest_process_true_when_argv_contains_pytest() -> None:
    """Return true when argv indicates pytest execution."""
    assert is_pytest_process(argv=["/build/.venv/bin/pytest", "-q"], env={})


def test_is_pytest_process_false_for_regular_server_process() -> None:
    """Return false when no pytest markers are present."""
    assert is_pytest_process(argv=["uvicorn", "server_app:app"], env={}) is False
