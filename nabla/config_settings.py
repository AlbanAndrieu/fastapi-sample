"""Application settings facade.

Domain-specific settings live under :mod:`nabla.settings`. This module preserves the
existing public imports used throughout the application while keeping configuration
construction free of network side effects.
"""

import json
import os
from functools import lru_cache
from typing import Annotated, Literal, Optional

from keycloak import KeycloakOpenID
from pydantic import AliasChoices, BeforeValidator, Field, SecretStr, field_validator

from nabla.feature_flags import (  # noqa: F401 -- compatibility facade exports
    STATSIG_API_KEY,
    UNLEASH_API_URL,
    UNLEASH_APP_NAME,
    UNLEASH_INSTANCE_ID,
    unleash_client as client,
    unleash_is_configured,
    unleash_requests_kwargs as _unleash_requests_kwargs,
    unleash_timeout_seconds,
)
from nabla.homelab_trusted_ip import parse_cidrs
from nabla.settings.base import unset_empty_env as _unset_empty_env
from nabla.settings.database import DatabaseSettings
from nabla.settings.models import AzureOpenAiInstance, DEFAULT_CHAT_MODEL, McpServerConfig
from nabla.utils.environment import env_bool
from nabla.utils.prometheus import PrometheusSettings
from nabla.version import API_VERSION, RELEASE_VERSION, RUNTIME_VERSION

APP_NAME = os.environ.get("APP_NAME", "fastapi-sample")
APP_PREFIX_VERSION = API_VERSION
APP_VERSION = RELEASE_VERSION
APP_RUNTIME_VERSION = RUNTIME_VERSION

EXPOSE_HOST = os.environ.get("EXPOSE_HOST", "0.0.0.0")  # noqa: S104 # nosec B104
EXPOSE_PORT = int(os.environ.get("EXPOSE_PORT", "8080"))
EXPOSE_MCP_PORT = int(os.environ.get("EXPOSE_MCP_PORT", "8001"))
_PYROSCOPE_SERVER_ADDRESS = os.environ.get("PYROSCOPE_SERVER_ADDRESS", "").strip()
PYROSCOPE_ENABLED = env_bool(
    "PYROSCOPE_ENABLED",
    default=bool(_PYROSCOPE_SERVER_ADDRESS),
)
PYROSCOPE_ENDPOINT = _PYROSCOPE_SERVER_ADDRESS or "http://localhost:4040"

DD_AGENT_HOST = os.environ.get("DD_AGENT_HOST", "127.0.0.1")
DD_TRACE_AGENT_PORT = os.environ.get("DD_TRACE_AGENT_PORT", "8126")
DD_TRACE_ENABLED = env_bool("DD_TRACE_ENABLED")
DD_PROFILING_ENABLED = env_bool("DD_PROFILING_ENABLED")
DD_TRACE_AGENT_URL = os.environ.get("DD_TRACE_AGENT_URL", "")
REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")

OTEL_SDK_DISABLED = env_bool("OTEL_SDK_DISABLED", default=True)
OTLP_GRPC_ENDPOINT = os.environ.get("OTLP_GRPC_ENDPOINT", "")
OTEL_EXPORTER_JAEGER_AGENT_HOST = os.environ.get(
    "OTEL_EXPORTER_JAEGER_AGENT_HOST",
    "jaeger-collector-grpc.service.gra.dev.consul",
)
OTEL_EXPORTER_JAEGER_AGENT_PORT = os.environ.get(
    "OTEL_EXPORTER_JAEGER_AGENT_PORT",
    "80",
)
OTEL_EXPORTER_JAEGER_ENDPOINT = os.environ.get(
    "OTEL_EXPORTER_JAEGER_ENDPOINT",
    "http://jaeger-collector-grpc.service.gra.dev.consul:14250",
)

SENTRY_DSN = os.environ.get(
    "SENTRY_DSN",
    "https://11c5d815632831d3274c830441885207@o4505783360356352.ingest.us.sentry.io/4505783364681728",
)
APP_DOMAIN = os.environ.get("APP_DOMAIN", "")

_ALBANDRIEU_PUBLIC_DOMAIN_SUFFIX = "albandrieu.com"


def _default_sickz_targets_value() -> str:
    """Return default pfSense WAN/LAN aliases for the inverse health probe."""
    return "https://home.albandrieu.com:10443/|https://172.17.0.1:10443/"


class _Settings(DatabaseSettings):
    """Non-database application settings."""

    tavily_api_key: Annotated[
        Optional[SecretStr],
        Field(default=None, validation_alias=AliasChoices("TAVILY_API_KEY")),
    ]
    brave_api_key: Annotated[
        Optional[SecretStr],
        Field(default=None, validation_alias=AliasChoices("BRAVE_API_KEY")),
    ]
    google_search_api_key: Annotated[
        Optional[SecretStr],
        Field(default=None, validation_alias=AliasChoices("GOOGLE_SEARCH_API_KEY")),
    ]
    google_search_cx: Annotated[
        Optional[str],
        Field(
            default=None,
            validation_alias=AliasChoices(
                "GOOGLE_SEARCH_CX",
                "GOOGLE_CSE_ID",
                "GOOGLE_SEARCH_ENGINE_ID",
            ),
        ),
    ]
    web_search_max_results: Annotated[
        int,
        Field(
            default=5,
            ge=1,
            le=5,
            validation_alias=AliasChoices(
                "WEB_SEARCH_MAX_RESULTS",
                "SEARCH_MAX_RESULTS",
                "MAX_SEARCH_RESULTS",
            ),
        ),
    ]

    mcp_clients: Annotated[
        list[McpServerConfig],
        Field(default_factory=list, validation_alias=AliasChoices("MCP_CLIENTS")),
    ]

    @field_validator("mcp_clients", mode="before")
    @classmethod
    def _coerce_mcp_clients(cls, value: object) -> object:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            return json.loads(stripped)
        return value

    a2a_public_base_url: Annotated[
        Optional[str],
        BeforeValidator(_unset_empty_env),
        Field(default=None, validation_alias=AliasChoices("A2A_PUBLIC_BASE_URL")),
    ]
    mcp_ops_key: Annotated[
        Optional[SecretStr],
        Field(default=None, validation_alias=AliasChoices("MCP_OPS_KEY")),
    ]
    mcp_ops_require_key: Annotated[
        bool,
        Field(default=False, validation_alias=AliasChoices("MCP_OPS_REQUIRE_KEY")),
    ]
    admin_access_key: Annotated[
        Optional[SecretStr],
        BeforeValidator(_unset_empty_env),
        Field(
            default=None,
            validation_alias=AliasChoices("ADMIN_ACCESS_KEY"),
        ),
    ]
    diagnostics_access_key: Annotated[
        Optional[SecretStr],
        BeforeValidator(_unset_empty_env),
        Field(
            default=None,
            validation_alias=AliasChoices("DIAGNOSTICS_ACCESS_KEY"),
        ),
    ]
    ops_route_policy_strict: Annotated[
        bool,
        Field(default=False, validation_alias=AliasChoices("OPS_ROUTE_POLICY_STRICT")),
    ]
    homelab_trusted_proxy_cidrs: Annotated[
        str,
        Field(default="", validation_alias=AliasChoices("HOMELAB_TRUSTED_PROXY_CIDRS")),
    ]

    @field_validator("homelab_trusted_proxy_cidrs")
    @classmethod
    def _validate_homelab_proxy_cidrs(cls, value: str) -> str:
        if value.strip():
            parse_cidrs(value)
        return value.strip()

    homelab_trusted_cidrs: Annotated[
        str,
        Field(default="", validation_alias=AliasChoices("HOMELAB_TRUSTED_CIDRS")),
    ]

    @field_validator("homelab_trusted_cidrs")
    @classmethod
    def _validate_homelab_trusted_cidrs(cls, value: str) -> str:
        if value.strip():
            parse_cidrs(value)
        return value.strip()

    ops_access_issuer: Annotated[
        Optional[str],
        Field(default=None, validation_alias=AliasChoices("OPS_ACCESS_ISSUER")),
    ]
    ops_access_aud: Annotated[
        Optional[str],
        Field(default=None, validation_alias=AliasChoices("OPS_ACCESS_AUD")),
    ]
    ops_access_owner_subjects: Annotated[
        Optional[str],
        Field(default=None, validation_alias=AliasChoices("OPS_ACCESS_OWNER_SUBJECTS")),
    ]

    appwrite_endpoint: Annotated[
        Optional[str],
        Field(default=None, validation_alias=AliasChoices("APPWRITE_ENDPOINT")),
    ]
    appwrite_project_id: Annotated[
        Optional[str],
        Field(default=None, validation_alias=AliasChoices("APPWRITE_PROJECT_ID")),
    ]
    appwrite_api_key: Annotated[
        Optional[SecretStr],
        Field(default=None, validation_alias=AliasChoices("APPWRITE_API_KEY")),
    ]

    sickz_targets: Annotated[
        str,
        Field(
            default_factory=_default_sickz_targets_value,
            validation_alias=AliasChoices("SICKZ_TARGETS"),
        ),
    ]
    sickz_internal_network: Annotated[
        bool,
        Field(default=False, validation_alias=AliasChoices("SICKZ_INTERNAL_NETWORK")),
    ]
    sickz_network_label: Annotated[
        Optional[str],
        Field(default=None, validation_alias=AliasChoices("SICKZ_NETWORK_LABEL")),
    ]

    litellm_url: Annotated[
        str,
        Field(default="", validation_alias=AliasChoices("LITELLM_URL")),
    ]
    litellm_api_key: Annotated[
        SecretStr,
        Field(
            default_factory=lambda: SecretStr(""),
            validation_alias=AliasChoices("LITELLM_API_KEY"),
        ),
    ]
    litellm_healthz_url: Annotated[
        str,
        Field(
            default="https://litellm.albandrieu.com",
            validation_alias=AliasChoices("LITELLM_HEALTHZ_URL"),
        ),
    ]
    default_chat_model: Annotated[
        str,
        Field(
            default=DEFAULT_CHAT_MODEL,
            validation_alias=AliasChoices("DEFAULT_CHAT_MODEL"),
            min_length=1,
        ),
    ]
    azure_openai_instance: dict[str, AzureOpenAiInstance] = {}

    ovh_username: Annotated[
        Optional[SecretStr],
        BeforeValidator(_unset_empty_env),
        Field(default="user-ALBANANDRIEU"),
    ]
    ovh_password: Annotated[
        Optional[SecretStr],
        BeforeValidator(_unset_empty_env),
        Field(default=None),
    ]
    ovh_project_name: Annotated[
        Optional[str],
        BeforeValidator(_unset_empty_env),
        Field(default=None),
    ]
    ovh_container: str = "nabla_models"

    @field_validator("ovh_username", mode="after")
    @classmethod
    def _ovh_username_non_empty_when_set(
        cls,
        value: Optional[SecretStr],
    ) -> Optional[SecretStr]:
        if value is not None and not value.get_secret_value().strip():
            raise ValueError("ovh_username, when set, cannot be blank")
        return value

    @field_validator("ovh_password", mode="after")
    @classmethod
    def _ovh_password_min_length_when_set(
        cls,
        value: Optional[SecretStr],
    ) -> Optional[SecretStr]:
        if value is not None and len(value.get_secret_value()) < 8:
            raise ValueError("ovh_password, when set, must be at least 8 characters")
        return value

    @field_validator("ovh_project_name", mode="after")
    @classmethod
    def _ovh_project_name_non_empty_when_set(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("ovh_project_name, when set, cannot be blank")
        return value

    oauth_token_secret: Annotated[SecretStr, Field(min_length=8)]
    # Keycloak is optional: without all four values, the auth routes answer 503
    # and /healthz reports the probe as skipped.
    keycloak_server_url: Annotated[Optional[str], Field(min_length=1)] = None
    keycloak_realm: Annotated[Optional[str], Field(min_length=1)] = None
    keycloak_client_id: Annotated[Optional[str], Field(min_length=1)] = None
    keycloak_client_secret: Annotated[Optional[SecretStr], Field(min_length=8)] = None

    metrics_enabled: bool = True
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


class APIDeploymentSettings(PrometheusSettings, _Settings):
    """Complete application deployment settings."""

    api_log_level: str = "INFO"
    scope: Literal["sample-V1", "sample-V2"] = "sample-V2"
    a2a_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("A2A_ENABLED"),
    )


@lru_cache()
def get_settings() -> APIDeploymentSettings:
    """Return the cached deployment settings instance."""
    return APIDeploymentSettings()  # pyright: ignore


def keycloak_configured() -> bool:
    """Return whether every Keycloak setting needed by the OpenID client is set."""
    settings = get_settings()
    return all(
        (
            settings.keycloak_server_url,
            settings.keycloak_realm,
            settings.keycloak_client_id,
            settings.keycloak_client_secret,
        ),
    )


@lru_cache()
def get_keycloak_openid() -> KeycloakOpenID:
    """Build the Keycloak OpenID client lazily; raise when Keycloak is not configured."""
    if not keycloak_configured():
        raise RuntimeError("Keycloak is not configured (KEYCLOAK_SERVER_URL/REALM/CLIENT_ID/CLIENT_SECRET)")
    settings = get_settings()
    return KeycloakOpenID(
        server_url=settings.keycloak_server_url,
        realm_name=settings.keycloak_realm,
        client_id=settings.keycloak_client_id,
        client_secret_key=settings.keycloak_client_secret.get_secret_value(),
    )


def get_openid_config():
    """Fetch Keycloak OpenID discovery configuration on explicit request."""
    return get_keycloak_openid().well_known()
