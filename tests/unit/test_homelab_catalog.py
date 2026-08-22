"""Contract tests for the typed homelab service catalog."""

import pytest
from pydantic import ValidationError

from nabla.api import homelab_catalog
from nabla.api.homelab_models import HomelabCatalog, HomelabDiscoverySource, HomelabService


def test_truenas_discovery_is_private_by_default() -> None:
    service = HomelabService.from_truenas_discovery(
        name="SABnzbd",
        source_id="sabnzbd",
        internal_host="172.17.0.24",
        internal_port=30025,
    )

    assert service.source is HomelabDiscoverySource.TRUENAS
    assert service.external is False
    assert service.endpoint_enabled is False
    assert service.tunnel_url is None
    assert service.public_https_probe_url is None


def test_external_access_requires_explicit_validated_opt_in() -> None:
    discovered = HomelabService.from_truenas_discovery(
        name="Open WebUI",
        source_id="open-webui",
        internal_host="172.17.0.24",
        internal_port=30044,
    )

    exposed = discovered.with_external_access("https://openwebui.albandrieu.com")

    assert exposed.external is True
    assert exposed.endpoint_enabled is True
    assert exposed.public_https_probe_url == "https://openwebui.albandrieu.com/"


def test_legacy_exposure_alias_is_accepted_but_not_emitted() -> None:
    service = HomelabService.model_validate(
        {
            "name": "Vaultwarden",
            "tunnelUrl": "https://vaultwarden.albandrieu.com",
            "reacheableFromOutside": True,
        }
    )

    payload = service.model_dump(mode="json", by_alias=True, exclude_none=True)

    assert service.external is True
    assert payload["external"] is True
    assert "reacheableFromOutside" not in payload


def test_conflicting_old_and_new_exposure_flags_fail_closed() -> None:
    with pytest.raises(ValidationError, match="external conflicts"):
        HomelabService.model_validate(
            {
                "name": "Conflicting service",
                "tunnelUrl": "https://example.com",
                "external": False,
                "reacheableFromOutside": True,
            }
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Missing URL", "external": True},
        {"name": "Cleartext", "external": True, "tunnelUrl": "http://example.com"},
        {
            "name": "Private DNS",
            "external": True,
            "tunnelUrl": "https://service.int.albandrieu.com",
        },
        {"name": "Private IP", "external": True, "tunnelUrl": "https://192.168.1.10"},
        {
            "name": "Credential leak",
            "external": True,
            "tunnelUrl": "https://user:secret@example.com",
        },
    ],
)
def test_invalid_external_exposure_is_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        HomelabService.model_validate(payload)


def test_stale_public_url_does_not_imply_external_exposure() -> None:
    service = HomelabService(
        name="SABnzbd",
        tunnel_url="https://sabnzbd.albandrieu.com",
        external=False,
    )

    assert service.public_https_probe_url is None


def test_sickz_only_uses_explicitly_external_https_services() -> None:
    private = HomelabService(
        name="SABnzbd",
        tunnel_url="https://sabnzbd.albandrieu.com",
        external=False,
    )
    public = HomelabService(
        name="Vaultwarden",
        tunnel_url="https://vaultwarden.albandrieu.com",
        external=True,
    )

    assert homelab_catalog._homelab_sickz_https_groups_from_services([private, public]) == [
        ["https://vaultwarden.albandrieu.com/"]
    ]


def test_catalog_rejects_duplicate_service_names_case_insensitively() -> None:
    with pytest.raises(ValidationError, match="duplicate homelab service name"):
        HomelabCatalog(
            services=[
                HomelabService(name="Grafana"),
                HomelabService(name="grafana"),
            ]
        )
