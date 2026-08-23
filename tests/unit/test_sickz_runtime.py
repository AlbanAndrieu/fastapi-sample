"""Tests for sickz PaaS detection and effective internal-network behavior."""

from types import SimpleNamespace

import pytest

from nabla.api import sickz_checks as sc


def _clear_paas_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in sc._KNOWN_PAAS_ENV_MARKERS:
        monkeypatch.delenv(name, raising=False)


def _settings(*, internal: bool = False, label: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        sickz_internal_network=internal,
        sickz_network_label=label,
    )


def test_parse_sickz_target_groups_preserves_aliases() -> None:
    assert sc.parse_sickz_target_groups(
        "https://one.example|https://two.example, https://three.example\n"
    ) == [
        ["https://one.example", "https://two.example"],
        ["https://three.example"],
    ]


def test_known_paas_marker_forces_external_probe_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_paas_env(monkeypatch)
    monkeypatch.setenv("VERCEL", "1")

    settings = _settings(internal=True)

    assert sc._known_paas_runtime_detected() is True
    assert sc._internal_network_effective(settings) is False


def test_explicit_internal_network_skips_without_paas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_paas_env(monkeypatch)

    settings = _settings(internal=True)

    assert sc._known_paas_runtime_detected() is False
    assert sc._internal_network_effective(settings) is True


def test_nabla_label_is_implicit_internal_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_paas_env(monkeypatch)

    settings = _settings(label="nabla")

    assert sc._implicit_internal_network(settings) is True
    assert sc._internal_network_implicit(settings) is True
    assert sc._internal_network_inferred_from(settings) == "SICKZ_NETWORK_LABEL=nabla"
    assert sc._internal_network_effective(settings) is True


def test_pfsense_group_is_always_present() -> None:
    groups = sc._ensure_pfsense_group([["https://vaultwarden.albandrieu.com/"]])

    assert sc._pfsense_canonical_href(groups[0]) == "https://home.albandrieu.com:10443/"
    assert groups[1] == ["https://vaultwarden.albandrieu.com/"]


def test_pfsense_group_is_not_duplicated() -> None:
    existing = sc._canonical_pfsense_alias_urls()

    groups = sc._ensure_pfsense_group([existing])

    assert groups == [existing]


def test_sickz_targets_equal_default_catalog_mode() -> None:
    from nabla.config_settings import _default_sickz_targets_value

    assert sc._targets_equal_default_catalog_mode(_default_sickz_targets_value()) is True
    assert sc._targets_equal_default_catalog_mode("https://example.com") is False
