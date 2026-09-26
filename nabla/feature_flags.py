"""Lazy feature-flag client construction.

Importing configuration must not contact external feature-flag services. Clients are
created and initialized only when their explicit getters are called.
"""

import os
import warnings
from functools import lru_cache
from typing import Any

import urllib3
from statsig_python_core import Statsig, StatsigOptions
from UnleashClient import UnleashClient

from nabla.settings.feature_flags import UnleashSettings

_IMPORT_UNLEASH_SETTINGS = UnleashSettings.from_mapping(os.environ)
UNLEASH_API_URL = _IMPORT_UNLEASH_SETTINGS.api_url
UNLEASH_APP_NAME = _IMPORT_UNLEASH_SETTINGS.unleash_app_name
UNLEASH_INSTANCE_ID = _IMPORT_UNLEASH_SETTINGS.instance_id
STATSIG_API_KEY = os.environ.get("STATSIG_API_KEY", "XXX")


def get_unleash_settings() -> UnleashSettings:
    """Return Unleash settings from the current process environment."""
    return UnleashSettings.from_mapping(os.environ)


def unleash_ssl_verify_enabled() -> bool:
    """Return whether Unleash HTTP clients should verify TLS certificates."""
    return get_unleash_settings().unleash_ssl_verify


def unleash_requests_kwargs(
    settings: UnleashSettings | None = None,
) -> dict[str, bool | str]:
    """Build requests options used by UnleashClient."""
    current = settings or get_unleash_settings()
    if current.unleash_ca_bundle:
        return {"verify": current.unleash_ca_bundle}
    if current.unleash_ssl_verify:
        return {"verify": True}
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    warnings.filterwarnings(
        "ignore",
        category=urllib3.exceptions.InsecureRequestWarning,
    )
    return {"verify": False}


def unleash_timeout_seconds() -> int:
    """Return the configured Unleash request timeout."""
    return get_unleash_settings().unleash_request_timeout


def unleash_is_configured() -> bool:
    """Return whether current Unleash credentials are usable."""
    return get_unleash_settings().configured


@lru_cache(maxsize=1)
def get_unleash_client() -> UnleashClient:
    """Create and initialize the Unleash client on first use only."""
    settings = get_unleash_settings()
    if not settings.configured:
        raise RuntimeError(
            "UNLEASH_INSTANCE_ID must be configured when UNLEASH_ENABLED=true",
        )

    client = UnleashClient(
        url=settings.api_url,
        app_name=settings.unleash_app_name,
        instance_id=settings.instance_id,
        refresh_interval=settings.unleash_refresh_interval,
        metrics_interval=settings.unleash_metrics_interval,
        request_timeout=settings.unleash_request_timeout,
        request_retries=settings.unleash_request_retries,
        custom_options=unleash_requests_kwargs(settings),
        disable_metrics=settings.unleash_disable_metrics,
    )
    client.initialize_client()
    return client


class LazyUnleashClient:
    """Compatibility proxy that defers Unleash construction until first use."""

    def __getattr__(self, name: str) -> Any:
        return getattr(get_unleash_client(), name)


unleash_client = LazyUnleashClient()


@lru_cache(maxsize=1)
def get_statsig_client() -> Statsig:
    """Create and initialize Statsig on first explicit use only."""
    options = StatsigOptions()
    options.environment = os.environ.get("STATSIG_ENVIRONMENT", "development")
    statsig = Statsig(STATSIG_API_KEY, options)
    statsig.initialize().wait()
    return statsig
