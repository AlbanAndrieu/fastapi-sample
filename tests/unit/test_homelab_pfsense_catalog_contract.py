"""Cross-repository contract checks for the effective pfSense/Home exposure policy."""

from nabla.api import homelab_catalog


def test_bootstrap_home_applies_direct_pfsense_override() -> None:
    """The packaged fallback must not expose legacy tunnel metadata to consumers."""
    homelab_catalog.clear_homelab_catalog_cache()
    try:
        catalog = homelab_catalog._load_bootstrap_catalog()
        by_name = {service.name: service for service in catalog.services}
        home = by_name["Home"]

        assert home.tunnel_url == "https://home.albandrieu.com:10443"
        assert home.external is False
        assert home.tunnel_secure is False
        assert home.effective_cloudflare_access_required is False
        assert home.security_exception is not None
        home_exception = home.security_exception.lower()
        assert "source" in home_exception
        assert "approved" in home_exception
        assert "fastapi cloud" in home_exception
    finally:
        homelab_catalog.clear_homelab_catalog_cache()


def test_bootstrap_pfsense_keeps_trusted_source_exception() -> None:
    homelab_catalog.clear_homelab_catalog_cache()
    try:
        catalog = homelab_catalog._load_bootstrap_catalog()
        by_name = {service.name: service for service in catalog.services}
        pfsense = by_name["pfSense"]

        assert pfsense.external is False
        assert pfsense.tunnel_secure is False
        assert pfsense.effective_cloudflare_access_required is False
        assert pfsense.security_exception is not None
        pfsense_exception = pfsense.security_exception.lower()
        assert "trusted" in pfsense_exception
        assert "source" in pfsense_exception
        assert "least-privilege" in pfsense_exception
        assert "10443" in pfsense_exception
    finally:
        homelab_catalog.clear_homelab_catalog_cache()
