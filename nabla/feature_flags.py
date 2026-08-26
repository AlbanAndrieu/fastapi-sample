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

UNLEASH_API_URL = os.environ.get(
    "UNLEASH_API_URL",
    "https://gitlab.com/api/v4/feature_flags/unleash/46788175",
)
UNLEASH_APP_NAME = os.environ.get("UNLEASH_APP_NAME", "staging")
UNLEASH_INSTANCE_ID = os.environ.get("UNLEASH_INSTANCE_ID", "")
STATSIG_API_KEY = os.environ.get("STATSIG_API_KEY", "XXX")

_PLACEHOLDER_CREDENTIALS = frozenset({"", "xxx", "changeme", "change-me"})


def env_bool(name: str, default: bool) -> bool:
    """Read a permissive boolean environment variable."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.lower() in ("true", "1", "yes")


def unleash_ssl_verify_enabled() -> bool:
    """Return whether Unleash HTTP clients should verify TLS certificates."""
    raw = os.environ.get("UNLEASH_SSL_VERIFY")
    if raw is None:
        return True
    stripped = raw.strip().lower()
    if stripped in ("", "true", "1", "yes", "on"):
        return True
    if stripped in ("false", "0", "no", "off"):
        return False
    return True


def unleash_requests_kwargs() -> dict[str, bool | str]:
    """Build requests options used by UnleashClient."""
    ca_bundle = (os.environ.get("UNLEASH_CA_BUNDLE") or "").strip()
    if ca_bundle:
        return {"verify": ca_bundle}
    if unleash_ssl_verify_enabled():
        return {"verify": True}
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    warnings.filterwarnings(
        "ignore",
        category=urllib3.exceptions.InsecureRequestWarning,
    )
    return {"verify": False}


def unleash_timeout_seconds() -> int:
    """Return the configured Unleash request timeout."""
    return int(os.environ.get("UNLEASH_REQUEST_TIMEOUT", "45"))


def unleash_is_configured() -> bool:
    """Return whether Unleash has a non-placeholder client instance ID."""
    instance_id = os.environ.get("UNLEASH_INSTANCE_ID", UNLEASH_INSTANCE_ID)
    return instance_id.strip().lower() not in _PLACEHOLDER_CREDENTIALS


@lru_cache(maxsize=1)
def get_unleash_client() -> UnleashClient:
    """Create and initialize the Unleash client on first use only."""
    if not unleash_is_configured():
        raise RuntimeError("UNLEASH_INSTANCE_ID must be configured when UNLEASH_ENABLED=true")

    client = UnleashClient(
        url=UNLEASH_API_URL.rstrip("/"),
        app_name=UNLEASH_APP_NAME,
        instance_id=os.environ.get("UNLEASH_INSTANCE_ID", UNLEASH_INSTANCE_ID),
        refresh_interval=int(os.environ.get("UNLEASH_REFRESH_INTERVAL", "60")),
        metrics_interval=int(os.environ.get("UNLEASH_METRICS_INTERVAL", "90")),
        request_timeout=unleash_timeout_seconds(),
        request_retries=int(os.environ.get("UNLEASH_REQUEST_RETRIES", "4")),
        custom_options=unleash_requests_kwargs(),
        disable_metrics=env_bool("UNLEASH_DISABLE_METRICS", False),
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
