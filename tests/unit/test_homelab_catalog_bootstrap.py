"""Bootstrap snapshot contracts for the homelab service catalog."""

from nabla.api import homelab_catalog


def test_bootstrap_catalog_preserves_litellm_and_garage_exposure_policy() -> None:
    catalog = homelab_catalog._load_bootstrap_catalog()
    by_name = {service.name: service for service in catalog.services}

    assert by_name["LiteLLM"].external is True
    assert by_name["LiteLLM"].internal_port == 4000
    assert by_name["LiteLLM - albandrieu"].external is False
    assert by_name["LiteLLM - albandrieu"].internal_port == 4000
    assert by_name["Home"].tunnel_url == "https://home.albandrieu.com:10443"
    assert by_name["Home"].external is False

    s3 = by_name["Garage S3"]
    assert s3.service_id == "garage"
    assert s3.internal_host == "172.17.0.24"
    assert s3.internal_port == 3900
    assert s3.tunnel_url == "https://s3.int.albandrieu.com"

    webui = by_name["Garage"]
    assert webui.service_id == "garage-webui"
    assert webui.internal_port == 3909
    assert webui.tunnel_url == "https://garage.albandrieu.com"

    admin = by_name["Garage Admin"]
    assert admin.service_id == "garage-admin"
    assert admin.internal_port == 3903
    assert admin.tunnel_url == "https://garage-admin.albandrieu.com"


def test_bootstrap_catalog_keeps_canonical_languagetool_private_http_probe() -> None:
    services = list(homelab_catalog._load_bootstrap_catalog().services)
    matches = [service for service in services if service.service_id == "languagetool"]

    assert len(matches) == 1
    languagetool = matches[0]
    assert languagetool.name == "LanguageTool"
    assert languagetool.internal_host == "172.17.0.24"
    assert languagetool.internal_port == 8010
    assert languagetool.internal_secure is False
    assert languagetool.internal_path == "/v2/check?language=en-US&text=healthcheck"
    assert languagetool.external is False
    assert languagetool.tunnel_url is None


def test_bootstrap_catalog_routes_2fauth_to_healthz_and_policy_aware_sickz() -> None:
    services = list(homelab_catalog._load_bootstrap_catalog().services)
    by_name = {service.name: service for service in services}
    twofa = by_name["2FAuth"]

    assert twofa.external is True
    assert twofa.public_https_probe_url == "https://2fauth.albandrieu.com/"
    assert twofa.effective_cloudflare_access_required is True
    sickz_groups = homelab_catalog._homelab_sickz_https_groups_from_services(services)
    assert ["https://2fauth.albandrieu.com/"] in sickz_groups


def test_bootstrap_catalog_applies_reviewed_exposure_overrides() -> None:
    services = list(homelab_catalog._load_bootstrap_catalog().services)
    by_name = {service.name: service for service in services}

    truenas = by_name["TrueNAS"]
    assert truenas.tunnel_url == "https://truenas.albandrieu.com:7000"
    assert truenas.public_https_probe_url == "https://truenas.albandrieu.com:7000/"
    assert truenas.external is True
    assert truenas.tunnel_secure is False

    s3 = by_name["Garage S3"]
    assert s3.tunnel_url == "https://s3.int.albandrieu.com"
    assert s3.external is True
    assert s3.tunnel_secure is False
    assert s3.effective_cloudflare_access_required is False
    assert s3.security_exception is not None

    webui = by_name["Garage"]
    assert webui.tunnel_url == "https://garage.albandrieu.com"
    assert webui.external is True
    assert webui.tunnel_secure is True
    assert webui.effective_cloudflare_access_required is True

    admin = by_name["Garage Admin"]
    assert admin.tunnel_url == "https://garage-admin.albandrieu.com"
    assert admin.external is True
    assert admin.tunnel_secure is True
    assert admin.effective_cloudflare_access_required is True

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


def test_bootstrap_catalog_uses_canonical_prometheus_reactive_and_traefik_targets() -> None:
    services = {service.name: service for service in homelab_catalog._load_bootstrap_catalog().services}

    assert "Prometheus - albandrieu" not in services

    prometheus = services["Prometheus"]
    assert prometheus.internal_host == "172.17.0.24"
    assert prometheus.internal_port == 9090
    assert prometheus.internal_path == "/-/ready"
    assert prometheus.public_https_probe_url == "https://prometheus.albandrieu.com/-/ready"

    reactive = services["Reactive Resume"]
    assert reactive.public_https_probe_url == "https://reactive.albandrieu.com/api/health"

    traefik = services["Traefik"]
    assert traefik.internal_host == "172.17.0.24"
    assert traefik.internal_port == 443
    assert traefik.external is False
    assert traefik.endpoint_enabled is False
