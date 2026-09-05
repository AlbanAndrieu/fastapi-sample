"""Tests for sickz PaaS detection and effective internal-network behavior."""

from types import SimpleNamespace

import pytest

from nabla.api import runtime_environment as runtime_env
from nabla.api import sickz_checks as sc
from nabla.api import sickz_pfsense as sp
from nabla.config_settings import _default_sickz_targets_value


def _clear_paas_env(monkeypatch: pytest.MonkeyPatch) -> None:
    names = (
        *runtime_env._KNOWN_PAAS_ENV_MARKERS,
        *runtime_env._FASTAPI_CLOUD_ENV_MARKERS,
        "SICKZ_NETWORK_LABEL",
    )
    for name in names:
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


def test_known_paas_marker_forces_external_probe_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_paas_env(monkeypatch)
    monkeypatch.setenv("VERCEL", "1")
    settings = _settings(internal=True)
    assert sp.known_paas_runtime_detected() is True
    assert sc._internal_network_effective(settings) is False


def test_explicit_internal_network_skips_without_paas(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_paas_env(monkeypatch)
    settings = _settings(internal=True)
    assert sp.known_paas_runtime_detected() is False
    assert sc._internal_network_effective(settings) is True


def test_nabla_label_is_implicit_internal_network(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_paas_env(monkeypatch)
    settings = _settings(label="nabla")
    assert sc._implicit_internal_network(settings) is True
    assert sc._internal_network_implicit(settings) is True
    assert sc._internal_network_inferred_from(settings) == "SICKZ_NETWORK_LABEL=nabla"
    assert sc._internal_network_effective(settings) is True


def test_pfsense_group_is_always_present() -> None:
    groups = sp.ensure_pfsense_group(
        [["https://vaultwarden.albandrieu.com/"]],
        default_targets=_default_sickz_targets_value(),
    )
    assert sp.pfsense_canonical_href(groups[0]) == "https://home.albandrieu.com:10443/"
    assert groups[1] == ["https://vaultwarden.albandrieu.com/"]


def test_pfsense_group_is_not_duplicated() -> None:
    existing = sp.canonical_pfsense_alias_urls(_default_sickz_targets_value())
    groups = sp.ensure_pfsense_group(
        [existing], default_targets=_default_sickz_targets_value()
    )
    assert groups == [existing]


def test_sickz_targets_equal_default_catalog_mode() -> None:
    assert sc._targets_equal_default_catalog_mode(_default_sickz_targets_value()) is True
    assert sc._targets_equal_default_catalog_mode("https://example.com") is False


def test_public_port_catalog_uses_litellm_4000_not_4100() -> None:
    assert 4000 in sp.PFSENSE_EXTRA_TCP_PORTS
    assert 4100 not in sp.PFSENSE_EXTRA_TCP_PORTS


def test_known_public_port_policy_matches_expected_exposure() -> None:
    policy = sp.pfsense_tcp_port_policy_payload()
    assert policy["22"]["service"] == "SSH"
    assert policy["22"]["expected_reachable"] is False
    assert policy["9922"]["service"] == "TrueNAS SSH"
    assert policy["9922"]["expected_reachable"] is False
    assert policy["4000"]["service"] == "LiteLLM"
    assert policy["4000"]["expected_reachable"] is False
    assert policy["7000"]["service"] == "TrueNAS via pfSense HAProxy"
    assert policy["7000"]["expected_reachable"] is True
    assert policy["7000"]["access_policy"] == "trusted_sources_only"
    assert policy["7000"]["default_action"] == "deny"
    assert policy["10443"]["service"] == "pfSense Admin/API"
    assert policy["10443"]["expected_reachable"] is True
    assert policy["10443"]["access_policy"] == "trusted_sources_only"
    assert policy["10443"]["default_action"] == "deny"
    assert policy["10443"]["negative_probe_required"] is True
    assert policy["10443"]["direct_probe_semantics"] == "diagnostic_only"
    assert policy["10443"]["recommended_control_path"] == "out_of_band"


@pytest.mark.asyncio
async def test_unknown_tcp_port_is_indeterminate_on_paas(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_paas_env(monkeypatch)
    monkeypatch.setenv("VERCEL", "1")

    async def fail_if_called(*_args: object, **_kwargs: object) -> bool:
        raise AssertionError("raw TCP probe must not run for unknown ports on PaaS")

    monkeypatch.setattr(sp, "_probe_tcp_port_open", fail_if_called)
    assert await sp.probe_pfsense_tcp_port("home.albandrieu.com", 8080) is None


@pytest.mark.asyncio
async def test_known_ports_dispatch_to_protocol_aware_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_ssh(_host: str, _port: int, **_kwargs: object) -> bool:
        return True

    async def fake_http(
        _host: str,
        _port: int,
        *,
        secure: bool,
        **_kwargs: object,
    ) -> bool:
        return secure

    monkeypatch.setattr(sp, "_probe_ssh_port", fake_ssh)
    monkeypatch.setattr(sp, "_probe_http_port", fake_http)
    assert await sp.probe_pfsense_tcp_port("example.test", 22) is True
    assert await sp.probe_pfsense_tcp_port("example.test", 9922) is True
    assert await sp.probe_pfsense_tcp_port("example.test", 4000) is False
    assert await sp.probe_pfsense_tcp_port("example.test", 7000) is True
    assert await sp.probe_pfsense_tcp_port("example.test", 10443) is True
