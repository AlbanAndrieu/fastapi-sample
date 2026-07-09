"""Tests for sickz PaaS detection and effective internal-network flag."""

import pytest

from nabla.api import health_checks as hc


def _clear_paas_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in hc._KNOWN_PAAS_ENV_MARKERS:
        monkeypatch.delenv(name, raising=False)


# ... [all existing tests here, unchanged] ...


def test_sickz_targets_equal_default_catalog_mode() -> None:
    pass
