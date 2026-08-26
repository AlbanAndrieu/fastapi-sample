"""Tests for shared environment parsing."""

import pytest

from nabla.utils.environment import env_bool


@pytest.mark.parametrize("value", ["1", " true ", "YES", "on"])
def test_env_bool_accepts_explicit_true_values(value: str) -> None:
    assert env_bool("FLAG", environ={"FLAG": value}) is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "unexpected"])
def test_env_bool_does_not_treat_non_empty_false_values_as_true(value: str) -> None:
    assert env_bool("FLAG", environ={"FLAG": value}) is False


def test_env_bool_uses_default_for_missing_or_blank_values() -> None:
    assert env_bool("FLAG", default=True, environ={}) is True
    assert env_bool("FLAG", default=True, environ={"FLAG": "  "}) is True
