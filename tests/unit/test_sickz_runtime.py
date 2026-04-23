"""Tests for sickz PaaS detection and effective internal-network flag."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from nabla.api import health_checks as hc


def _clear_paas_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in hc._KNOWN_PAAS_ENV_MARKERS:
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize(
    "env_name",
    (
        "VERCEL",
        "AWS_EXECUTION_ENV",
        "AWS_LAMBDA_FUNCTION_NAME",
        "KUBERNETES_SERVICE_HOST",
        "FLY_APP_NAME",
        "RAILWAY_ENVIRONMENT",
        "RAILWAY_PROJECT_ID",
        "HEROKU_APP_NAME",
        "DYNO",
    ),
)
def test_known_paas_runtime_detected_true(monkeypatch: pytest.MonkeyPatch, env_name: str) -> None:
    _clear_paas_env(monkeypatch)
    monkeypatch.setenv(env_name, "1")
    assert hc._known_paas_runtime_detected() is True


def test_known_paas_runtime_detected_false_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_paas_env(monkeypatch)
    assert hc._known_paas_runtime_detected() is False


def test_known_paas_whitespace_only_env_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_paas_env(monkeypatch)
    monkeypatch.setenv("VERCEL", "   ")
    assert hc._known_paas_runtime_detected() is False


def test_effective_internal_false_on_paas(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_paas_env(monkeypatch)
    monkeypatch.setenv("VERCEL", "1")
    settings = SimpleNamespace(sickz_internal_network=True)
    assert hc._sickz_internal_network_effective(settings) is False  # type: ignore[arg-type]


def test_effective_internal_follows_config_when_not_paas(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_paas_env(monkeypatch)
    settings = SimpleNamespace(sickz_internal_network=True)
    assert hc._sickz_internal_network_effective(settings) is True  # type: ignore[arg-type]


def test_implicit_internal_from_nabla_label(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_paas_env(monkeypatch)
    settings = SimpleNamespace(sickz_internal_network=False, sickz_network_label="nabla")
    assert hc._sickz_internal_network_effective(settings) is True  # type: ignore[arg-type]
    assert hc._sickz_internal_network_implicit(settings) is True  # type: ignore[arg-type]
    assert hc._sickz_internal_network_inferred_from(settings) == "SICKZ_NETWORK_LABEL=nabla"  # type: ignore[arg-type]


def test_implicit_internal_from_app_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_paas_env(monkeypatch)
    monkeypatch.setattr(hc, "APP_DOMAIN", "albandrieu.albandrieu.com")
    settings = SimpleNamespace(sickz_internal_network=False, sickz_network_label=None)
    assert hc._sickz_internal_network_effective(settings) is True  # type: ignore[arg-type]
    assert hc._sickz_internal_network_inferred_from(settings) == "APP_DOMAIN=albandrieu.albandrieu.com"  # type: ignore[arg-type]


def test_implicit_internal_overridden_on_paas(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_paas_env(monkeypatch)
    monkeypatch.setenv("VERCEL", "1")
    settings = SimpleNamespace(sickz_internal_network=False, sickz_network_label="nabla")
    assert hc._sickz_internal_network_effective(settings) is False  # type: ignore[arg-type]


def test_sickz_pfsense_row_uses_home_href_and_label() -> None:
    urls = ["https://home.albandrieu.com:10443/", "https://172.17.0.1:10443/"]
    meta = hc._sickz_row_ui_metadata(urls)
    assert meta["display_label"] == "PfSense"
    assert meta["href"] == "https://home.albandrieu.com:10443/"
    assert meta["icon_filename"] == "pfsense.svg"


def test_build_sickz_payload_skipped_lists_configured_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    """LAN skip still returns each SICKZ group so UIs can show intended probes (yellow / not run)."""

    async def _run() -> dict:
        _clear_paas_env(monkeypatch)
        fake_settings = SimpleNamespace(
            sickz_internal_network=True,
            sickz_targets="https://alpha.example/,https://beta.example/|https://alt.beta/",
            sickz_network_label="",
        )
        monkeypatch.setattr(hc, "get_settings", lambda: fake_settings)
        request = MagicMock()
        request.app.version = "0.0.0-test"
        return await hc.build_sickz_payload(request)

    payload = asyncio.run(_run())
    assert payload["status"] == "skipped_internal_network"
    assert len(payload["checks"]) == 2
    for row in payload["checks"].values():
        assert row["skipped"] is True
        assert row["reason"]
        assert isinstance(row["aliases_probed"], list)
        assert row["aliases_probed"]
        assert row.get("display_label")
        assert row.get("href")
        assert row.get("icon_filename", "").endswith(".svg")
        assert row.get("tls_trusted") is None


def test_sickz_display_label_strips_personal_domain_suffix() -> None:
    assert hc._sickz_display_label(["https://adguardhome.albandrieu.com/"]) == "adguardhome"


def test_sickz_icon_filename_adguardhome() -> None:
    assert hc._sickz_icon_filename(["https://adguardhome.albandrieu.com/"]) == "adguard-home.svg"


def test_sickz_display_label_multi_alias() -> None:
    assert (
        hc._sickz_display_label(["https://a.albandrieu.com/", "https://b.albandrieu.com/"])
        == "a · b"
    )


def test_sickz_targets_equal_default_catalog_mode() -> None:
    from nabla.config_settings import _default_sickz_targets_value

    default = _default_sickz_targets_value()
    assert hc._sickz_targets_equal_default_catalog_mode(default)
    assert hc._sickz_targets_equal_default_catalog_mode(f"\n{default}\n")
    assert not hc._sickz_targets_equal_default_catalog_mode(f"{default},https://extra.example/")
