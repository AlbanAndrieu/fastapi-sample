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

    assert service.service_id == "sabnzbd"
    assert service.source is HomelabDiscoverySource.TRUENAS
    assert service.external is False
    assert service.endpoint_enabled is False
    assert service.tunnel_url is None
    assert service.public_https_probe_url is None


def test_legacy_catalog_derives_id_from_public_hostname() -> None:
    service = HomelabService.model_validate(
        {
            "name": "Langfuse",
            "tunnelUrl": "https://langfuse.albandrieu.com",
            "external": True,
        },
    )

    payload = service.model_dump(mode="json", by_alias=True, exclude_none=True)

    assert service.service_id == "langfuse"
    assert payload["id"] == "langfuse"
    assert payload["tunnelUrl"] == "https://langfuse.albandrieu.com"


def test_legacy_private_service_derives_id_from_name() -> None:
    service = HomelabService.model_validate(
        {
            "name": "Open SpeedTest",
            "internalHost": "172.17.0.24",
            "internalPort": 30117,
            "external": False,
        },
    )

    assert service.service_id == "open-speedtest"


def test_explicit_service_id_is_preserved() -> None:
    service = HomelabService.model_validate(
        {
            "id": "langfuse-worker",
            "name": "Langfuse UI",
            "external": False,
        },
    )

    assert service.service_id == "langfuse-worker"


def test_external_access_requires_explicit_validated_opt_in() -> None:
    discovered = HomelabService.from_truenas_discovery(
        name="Open WebUI",
        source_id="open-webui",
        internal_host="172.17.0.24",
        internal_port=30044,
    )

    exposed = discovered.with_external_access("https://openwebui.albandrieu.com")

    assert exposed.service_id == "open-webui"
    assert exposed.external is True
    assert exposed.endpoint_enabled is True
    assert exposed.public_https_probe_url == "https://openwebui.albandrieu.com/"


def test_legacy_exposure_alias_is_accepted_but_not_emitted() -> None:
    service = HomelabService.model_validate(
        {
            "name": "Vaultwarden",
            "tunnelUrl": "https://vaultwarden.albandrieu.com",
            "reacheableFromOutside": True,
        },
    )

    payload = service.model_dump(mode="json", by_alias=True, exclude_none=True)

    assert service.external is True
    assert payload["id"] == "vaultwarden"
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
            },
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Missing URL", "external": True},
        {"name": "Cleartext", "external": True, "tunnelUrl": "http://example.com"},
        {
            "name": "Unqualified direct ingress",
            "external": True,
            "tunnelUrl": "https://service.int.albandrieu.com",
        },
        {"name": "Private IP", "external": True, "tunnelUrl": "https://192.168.1.10"},
        {
            "name": "Credential leak",
            "external": True,
            "tunnelUrl": "https://" + "user" + ":" + "secret" + "@example.com",
        },
    ],
)
def test_invalid_external_exposure_is_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        HomelabService.model_validate(payload)


def test_int_external_exception_requires_explicit_direct_security_posture() -> None:
    service = HomelabService.model_validate(
        {
            "name": "Garage",
            "tunnelUrl": "https://garage.int.albandrieu.com",
            "external": True,
            "tunnelSecure": False,
        },
    )

    assert service.external is True
    assert service.tunnel_secure is False
    assert service.public_https_probe_url == "https://garage.int.albandrieu.com/"


def test_secure_external_service_requires_cloudflare_access_by_default() -> None:
    service = HomelabService(
        name="2FAuth",
        tunnel_url="https://2fauth.albandrieu.com",
        tunnel_secure=True,
        external=True,
    )

    assert service.effective_cloudflare_access_required is True


def test_direct_external_service_does_not_require_access_by_default() -> None:
    service = HomelabService(
        name="Garage",
        tunnel_url="https://garage.int.albandrieu.com",
        tunnel_secure=False,
        external=True,
    )

    assert service.effective_cloudflare_access_required is False


def test_stale_public_url_does_not_imply_external_exposure() -> None:
    service = HomelabService(
        name="SABnzbd",
        tunnel_url="https://sabnzbd.albandrieu.com",
        external=False,
    )

    assert service.public_https_probe_url is None


def test_sickz_uses_all_declared_https_exposure_targets() -> None:
    private = HomelabService(
        name="SABnzbd",
        tunnel_url="https://sabnzbd.albandrieu.com",
        external=False,
    )
    public = HomelabService(
        name="2FAuth",
        tunnel_url="https://2fauth.albandrieu.com",
        external=True,
    )

    assert homelab_catalog._homelab_sickz_https_groups_from_services([private, public]) == [
        ["https://sabnzbd.albandrieu.com/"],
        ["https://2fauth.albandrieu.com/"],
    ]


def test_sickz_metadata_keeps_names_for_policy_targets() -> None:
    private = HomelabService(
        name="SABnzbd",
        tunnel_url="https://sabnzbd.albandrieu.com",
        external=False,
        icon_src="assets/selfh-icons/sabnzbd.png",
    )

    assert homelab_catalog.homelab_tunnel_url_to_service_name([private]) == {
        "https://sabnzbd.albandrieu.com/": "SABnzbd",
    }
    assert homelab_catalog.homelab_tunnel_url_to_resolved_icon_src([private]) == {
        "https://sabnzbd.albandrieu.com/": "assets/selfh-icons/sabnzbd.png",
    }


def test_healthz_key_uses_stable_service_id() -> None:
    assert homelab_catalog._healthz_check_key("langfuse-worker") == ("albandrieu_langfuse_worker")


def test_catalog_rejects_duplicate_service_names_case_insensitively() -> None:
    with pytest.raises(ValidationError, match="duplicate homelab service name"):
        HomelabCatalog(
            services=[
                HomelabService(name="Grafana"),
                HomelabService(name="grafana"),
            ],
        )


def test_catalog_rejects_duplicate_service_ids() -> None:
    with pytest.raises(ValidationError, match="duplicate homelab service id"):
        HomelabCatalog(
            services=[
                HomelabService(id="langfuse", name="Langfuse UI"),
                HomelabService(id="langfuse", name="Langfuse Worker"),
            ],
        )


def test_exposure_catalog_is_packaged_with_fastapi() -> None:
    path = homelab_catalog.HOMELAB_SERVICES_CATALOG_PATH

    assert path.is_file()
    assert path.name == "homelab-services.json"
    assert path.parent.name == "data"
    assert homelab_catalog.HOMELAB_EXPOSURE_OVERRIDES_PATH.is_file()


@pytest.mark.asyncio
async def test_packaged_catalog_preserves_litellm_exposure_policy() -> None:
    catalog = await homelab_catalog.fetch_homelab_catalog()
    by_name = {service.name: service for service in catalog.services}

    assert by_name["LiteLLM"].external is True
    assert by_name["LiteLLM"].internal_port == 4000
    assert by_name["LiteLLM - albandrieu"].external is False
    assert by_name["LiteLLM - albandrieu"].internal_port == 4000
    assert by_name["Home"].tunnel_url == "https://home.albandrieu.com:10443"
    assert by_name["Home"].external is False


@pytest.mark.asyncio
async def test_packaged_catalog_routes_2fauth_to_healthz_and_policy_aware_sickz() -> None:
    services = await homelab_catalog.fetch_homelab_services()
    by_name = {service.name: service for service in services}
    twofa = by_name["2FAuth"]

    assert twofa.external is True
    assert twofa.public_https_probe_url == "https://2fauth.albandrieu.com/"
    assert twofa.effective_cloudflare_access_required is True
    sickz_groups = homelab_catalog._homelab_sickz_https_groups_from_services(services)
    assert ["https://2fauth.albandrieu.com/"] in sickz_groups


@pytest.mark.asyncio
async def test_packaged_catalog_applies_reviewed_exposure_overrides() -> None:
    services = await homelab_catalog.fetch_homelab_services()
    by_name = {service.name: service for service in services}

    garage = by_name["Garage"]
    assert garage.tunnel_url == "https://garage.int.albandrieu.com"
    assert garage.external is True
    assert garage.tunnel_secure is False
    assert garage.effective_cloudflare_access_required is False
    assert garage.security_exception is not None

    bichon = by_name["Bichon"]
    assert bichon.external is False
    assert bichon.tunnel_secure is False
    assert bichon.effective_cloudflare_access_required is False
    assert bichon.security_exception is not None

    n8n = by_name["n8n"]
    assert n8n.external is True
    assert n8n.tunnel_secure is True
    assert n8n.effective_cloudflare_access_required is True
    assert n8n.security_exception is not None
