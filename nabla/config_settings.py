"""Settings for nabla project"""

import json
import logging
import os
import warnings
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, ClassVar, Literal, Optional

import urllib3
from keycloak import KeycloakOpenID
from pydantic import (
    AliasChoices,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from statsig_python_core import (  # note underscores instead of hyphens in import
    Statsig,
    StatsigOptions,
)
from UnleashClient import UnleashClient

from nabla._version import get_versions
from nabla.db_config import (
    ensure_supavisor_pooler_username,
    is_supabase_postgres_host,
    is_supabase_supavisor_pooler_host,
    make_postgres_url,
    merge_postgres_query_sslmode_require,
    resolve_supabase_project_ref,
    supabase_session_pooler_targets,
)
from nabla.utils.prometheus import PrometheusSettings

_log = logging.getLogger(__name__)

APP_NAME = os.environ.get("APP_NAME", "fastapi-sample")
APP_PREFIX_VERSION = os.environ.get("APP_PREFIX_VERSION", "v")
APP_VERSION = get_versions()["version"]

EXPOSE_HOST = os.environ.get("EXPOSE_HOST", "0.0.0.0")  # noqa: S104 noqa:B104 # nosec B104
EXPOSE_PORT = int(os.environ.get("EXPOSE_PORT", "8080"))
EXPOSE_MCP_PORT = int(os.environ.get("EXPOSE_MCP_PORT", "8001"))
PYROSCOPE_ENDPOINT = os.environ.get("PYROSCOPE_SERVER_ADDRESS", "http://localhost:4040")

DD_AGENT_HOST = os.environ.get("DD_AGENT_HOST", "127.0.0.1")
DD_TRACE_AGENT_PORT = os.environ.get("DD_TRACE_AGENT_PORT", "8126")
DD_TRACE_ENABLED = os.environ.get("DD_TRACE_ENABLED", "false").lower() in (
    "true",
    "1",
    "yes",
)
# When unset/empty, ddtrace has no explicit agent URL; health probe skips instead of hitting localhost.
DD_TRACE_AGENT_URL = os.environ.get("DD_TRACE_AGENT_URL", "")

REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")

# http://grpc.jaeger-collector-grpc.service.gra.dev.consul
# http://jaeger-collector-grpc.service.gra.dev.consul:14250
# http://datadog-agent.service.gra.dev.consul:4317
# http://otel-collector.service.gra.dev.consul:9411/api/v2/spans

OTEL_SDK_DISABLED = os.environ.get("OTEL_SDK_DISABLED", "true").lower() in (
    "true",
    "1",
    "yes",
)
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

UNLEASH_API_URL = os.environ.get("UNLEASH_API_URL", "https://gitlab.com/api/v4/feature_flags/unleash/46788175")
UNLEASH_APP_NAME = os.environ.get("UNLEASH_APP_NAME", "staging")
UNLEASH_INSTANCE_ID = os.environ.get("UNLEASH_INSTANCE_ID", "XXX")

STATSIG_API_KEY = os.environ.get("STATSIG_API_KEY", "XXX")


def _unset_empty_env(value: Any) -> Any:
    """Treat blank env strings as unset so field defaults apply (pydantic-settings)."""
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.lower() in ("true", "1", "yes")


UNLEASH_ENABLED = _env_bool("UNLEASH_ENABLED", False)


def _unleash_ssl_verify_enabled() -> bool:
    """
    Whether Unleash HTTP clients should verify TLS certificates.

    Empty or unset ``UNLEASH_SSL_VERIFY`` must mean "verify" (secure default).
    Only explicit false-like values disable verification.
    """
    raw = os.environ.get("UNLEASH_SSL_VERIFY")
    if raw is None:
        return True
    stripped = raw.strip().lower()
    if stripped in ("", "true", "1", "yes", "on"):
        return True
    if stripped in ("false", "0", "no", "off"):
        return False
    return True


def _unleash_requests_kwargs() -> dict:
    """Extra kwargs for UnleashClient HTTP calls (passed to requests)."""
    ca_bundle = (os.environ.get("UNLEASH_CA_BUNDLE") or "").strip()
    if ca_bundle:
        return {"verify": ca_bundle}
    if _unleash_ssl_verify_enabled():
        return {"verify": True}
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    warnings.filterwarnings(
        "ignore",
        category=urllib3.exceptions.InsecureRequestWarning,
    )
    return {"verify": False}


def _openai_api_key_from_env() -> str:
    """Default OpenAI API key from the same env var as the OpenAI SDK."""
    return os.environ["OPENAI_API_KEY"]


class AzureOpenAiInstance(BaseModel):
    """
    Store the elements needed for creating an instance of OpenAI in Azure.
    """

    url: Annotated[
        # Limited in constraints; see https://github.com/pydantic/pydantic/issues/9440
        # Url,
        # UrlConstraints(
        #    allowed_schemes=["https"], host_required=True, default_port=None
        # ),
        str,
        Field(pattern=r"^https://[a-z0-9\-]+\.openai\.azure\.com$"),
    ]
    api_key: Annotated[str, Field(default_factory=_openai_api_key_from_env, min_length=1)]
    api_alias: Annotated[str, Field(min_length=1)]
    available_models: Annotated[str, Field(default="gpt-5", min_length=1)]


_ALBANDRIEU_PUBLIC_DOMAIN_SUFFIX = "albandrieu.com"


def _default_sickz_targets_value() -> str:
    """pfSense WAN + LAN aliases only; ``/sickz`` merges HTTPS tunnels from the homelab catalog when unchanged."""
    return "https://home.albandrieu.com:10443/|https://172.17.0.1:10443/"


DEFAULT_CHAT_MODEL = "gpt-4.1"


class McpServerConfig(BaseModel):
    """One external MCP server this app can spawn and call over stdio (e.g. OpenRAG ``openrag-mcp``)."""

    model_config = ConfigDict(extra="ignore")

    name: Annotated[str, Field(min_length=1, description="Logical name, e.g. ``openrag``.")]
    transport: Literal["stdio"] = "stdio"
    command: Annotated[str, Field(min_length=1, description="Executable, e.g. ``uvx`` or ``docker``.")]
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict, description="Extra env merged with a safe inherited subset.")
    cwd: str | None = Field(default=None, description="Optional working directory for the subprocess.")
    enabled: bool = True
    startup_timeout_seconds: float = Field(default=30.0, ge=1.0, le=300.0)
    tool_call_timeout_seconds: float = Field(default=120.0, ge=1.0, le=600.0)


# Basic db & ovh settings
class _Settings(BaseSettings):
    """
    Base Settings.

    It reads from the environment, .env or .env.local (in that order)
    and defined the following variables.
    """

    # Settings configuration
    __base_path: ClassVar[Path] = Path(__file__).parent.absolute()
    model_config = SettingsConfigDict(
        env_file=[__base_path / ".env", __base_path / ".env.local"],
        env_file_encoding="utf-8",
        extra="ignore",
        env_nested_delimiter="__",
    )

    # Postgres — built from POSTGRES_* (optional legacy DB_* aliases). No DATABASE_URL / DB_URL.
    postgres_driver: Annotated[
        str,
        Field(
            default="postgresql",
            description="SQLAlchemy / libpq driver prefix (postgresql, postgresql+psycopg stripped to postgresql for URIs).",
            min_length=1,
            validation_alias=AliasChoices("POSTGRES_DRIVER"),
        ),
    ]
    postgres_user: Annotated[
        str,
        Field(
            default="back",
            description="Database user.",
            min_length=1,
            validation_alias=AliasChoices("POSTGRES_USER", "DB_USER"),
        ),
    ]
    postgres_password: Annotated[
        SecretStr,
        Field(
            description="Database password.",
            min_length=8,
            validation_alias=AliasChoices("POSTGRES_PASSWORD", "DB_PASSWORD"),
        ),
    ] = SecretStr("backpass")  # nosec B104 — dev default only
    postgres_host: Annotated[
        str,
        Field(
            default="localhost",
            description="Database host (pooler or direct).",
            min_length=1,
            validation_alias=AliasChoices("POSTGRES_HOST", "DB_HOST"),
        ),
    ]
    postgres_port: Annotated[
        int,
        Field(
            default=5432,
            description="Database port.",
            validation_alias=AliasChoices("POSTGRES_PORT", "DB_PORT"),
        ),
    ]
    postgres_db: Annotated[
        str,
        Field(
            default="back",
            description="Database name.",
            min_length=1,
            validation_alias=AliasChoices("POSTGRES_DB", "DB_NAME"),
        ),
    ]
    postgres_query: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Optional URI query (e.g. pgbouncer=true for Supabase pooler).",
            validation_alias=AliasChoices("POSTGRES_QUERY"),
        ),
    ]

    postgres_migration_host: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Override host for migrations / sync engine (e.g. Supabase direct session).",
            validation_alias=AliasChoices("POSTGRES_MIGRATION_HOST"),
        ),
    ]
    postgres_migration_port: Annotated[
        Optional[int],
        Field(
            default=None,
            description="Override port for migrations.",
            validation_alias=AliasChoices("POSTGRES_MIGRATION_PORT"),
        ),
    ]
    postgres_migration_user: Annotated[
        Optional[str],
        Field(
            default=None,
            validation_alias=AliasChoices("POSTGRES_MIGRATION_USER"),
        ),
    ]
    postgres_migration_password: Annotated[
        Optional[SecretStr],
        Field(
            default=None,
            validation_alias=AliasChoices("POSTGRES_MIGRATION_PASSWORD"),
        ),
    ]
    postgres_migration_db: Annotated[
        Optional[str],
        Field(
            default=None,
            validation_alias=AliasChoices("POSTGRES_MIGRATION_DB"),
        ),
    ]
    postgres_migration_query: Annotated[
        Optional[str],
        Field(
            default=None,
            validation_alias=AliasChoices("POSTGRES_MIGRATION_QUERY"),
        ),
    ]
    supabase_pooler_region: Annotated[
        Optional[str],
        Field(
            default=None,
            description=(
                "Supavisor session pooler region (e.g. eu-west-3). Set when POSTGRES_HOST is "
                "db.<ref>.supabase.co and your network has no IPv6; uses aws-0-<region>.pooler.supabase.com."
            ),
            validation_alias=AliasChoices("SUPABASE_POOLER_REGION"),
        ),
    ]
    supabase_project_ref: Annotated[
        Optional[str],
        Field(
            default=None,
            description=("Supabase project ref for pooler username (postgres.<ref>). If unset, inferred from SUPABASE_URL or db.<ref>.supabase.co in POSTGRES_HOST."),
            validation_alias=AliasChoices(
                "SUPABASE_PROJECT_REF",
                "SUPABASE_PROJECT_ID",
            ),
        ),
    ]

    # Optional Supabase REST client (not used for SQL; use POSTGRES_* for DB).
    supabase_url: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Project URL, e.g. https://xxx.supabase.co",
            validation_alias=AliasChoices("SUPABASE_URL"),
        ),
    ]
    supabase_service_role_key: Annotated[
        Optional[SecretStr],
        Field(
            default=None,
            description="Service role JWT from Dashboard → API (not the CLI sbp_ token).",
            validation_alias=AliasChoices("SUPABASE_SERVICE_ROLE_KEY"),
        ),
    ]
    tavily_api_key: Annotated[
        Optional[SecretStr],
        Field(
            default=None,
            description="Tavily Search API key (https://tavily.com).",
            validation_alias=AliasChoices("TAVILY_API_KEY"),
        ),
    ]
    brave_api_key: Annotated[
        Optional[SecretStr],
        Field(
            default=None,
            description="Brave Search API subscription token (https://brave.com/search/api/).",
            validation_alias=AliasChoices("BRAVE_API_KEY"),
        ),
    ]
    google_search_api_key: Annotated[
        Optional[SecretStr],
        Field(
            default=None,
            description="Google API key for Custom Search JSON API.",
            validation_alias=AliasChoices("GOOGLE_SEARCH_API_KEY"),
        ),
    ]
    google_search_cx: Annotated[
        Optional[str],
        Field(
            default=None,
            description=("Programmable Search Engine ID (cx) for Google Custom Search; required with GOOGLE_SEARCH_API_KEY."),
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
            description="Maximum number of web-search results to retrieve (hard-capped to 5).",
            validation_alias=AliasChoices(
                "WEB_SEARCH_MAX_RESULTS",
                "SEARCH_MAX_RESULTS",
                "MAX_SEARCH_RESULTS",
            ),
        ),
    ]

    mcp_clients: Annotated[
        list[McpServerConfig],
        Field(
            default_factory=list,
            description=("External MCP servers (stdio). Set ``MCP_CLIENTS`` to a JSON array of objects with keys: name, command, args, env (optional), enabled (optional)."),
            validation_alias=AliasChoices("MCP_CLIENTS"),
        ),
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
        Field(
            default=None,
            description=("Public base URL for the Agent Card JSON-RPC interface (e.g. https://api.example.com). If unset, relative paths are used in the card."),
            validation_alias=AliasChoices("A2A_PUBLIC_BASE_URL"),
        ),
    ]

    mcp_ops_key: Annotated[
        Optional[SecretStr],
        Field(
            default=None,
            description="If set, ``/v1/mcp/ops/*`` requires header ``X-MCP-Ops-Key`` matching this secret.",
            validation_alias=AliasChoices("MCP_OPS_KEY"),
        ),
    ]

    appwrite_endpoint: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Appwrite API endpoint, e.g. https://<region>.cloud.appwrite.io/v1",
            validation_alias=AliasChoices("APPWRITE_ENDPOINT"),
        ),
    ]
    appwrite_project_id: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Appwrite project ID.",
            validation_alias=AliasChoices("APPWRITE_PROJECT_ID"),
        ),
    ]
    appwrite_api_key: Annotated[
        Optional[SecretStr],
        Field(
            default=None,
            description="Appwrite server API key.",
            validation_alias=AliasChoices("APPWRITE_API_KEY"),
        ),
    ]
    sickz_targets: Annotated[
        str,
        Field(
            default_factory=_default_sickz_targets_value,
            description=(
                "Comma- or newline-separated *groups* for GET /sickz. Within a group, use | between "
                "equivalent URLs (e.g. pfSense hostname and Docker bridge IP on the same LAN). "
                "The group fails if *any* alias responds. Probes use verify=False so TLS cert issues "
                "do not hide reachability. Default is pfSense only; when left at that default, "
                "GET /sickz merges HTTPS ``tunnelUrl`` entries from the homelab services JSON (except pfSense). "
                "Set SICKZ_TARGETS to override or clear."
            ),
            validation_alias=AliasChoices("SICKZ_TARGETS"),
        ),
    ]
    sickz_internal_network: Annotated[
        bool,
        Field(
            default=False,
            description=(
                "When true, sickz HTTP probes are skipped (home LAN). Also skipped implicitly when "
                "SICKZ_NETWORK_LABEL is 'nabla' or APP_DOMAIN is albandrieu.albandrieu.com, unless a PaaS runtime is detected."
            ),
            validation_alias=AliasChoices("SICKZ_INTERNAL_NETWORK"),
        ),
    ]
    sickz_network_label: Annotated[
        Optional[str],
        Field(
            default=None,
            description=(
                "Human-readable name for sickz messages; falls back to APP_DOMAIN when unset. "
                "Exact value 'nabla' (case-insensitive) implies home LAN for sickz skip (same as SICKZ_INTERNAL_NETWORK) unless on PaaS."
            ),
            validation_alias=AliasChoices("SICKZ_NETWORK_LABEL"),
        ),
    ]

    litellm_url: Annotated[
        str,
        Field(
            default="",
            description=(
                "LiteLLM OpenAI-compatible proxy base URL without a path (e.g. http://172.17.0.57:4100). "
                "When set, LLM chat uses this endpoint before Azure OpenAI or direct OpenAI."
            ),
            validation_alias=AliasChoices("LITELLM_URL"),
        ),
    ]
    litellm_api_key: Annotated[
        SecretStr,
        Field(
            default_factory=lambda: SecretStr(""),
            description="API key for the LiteLLM proxy; leave unset or empty when the proxy does not require auth.",
            validation_alias=AliasChoices("LITELLM_API_KEY"),
        ),
    ]
    litellm_healthz_url: Annotated[
        str,
        Field(
            default="https://litellm.albandrieu.com",
            description=("Public LiteLLM proxy origin (no path) for GET /healthz checks (e.g. …/health/liveliness). Set empty to skip the litellm probe."),
            validation_alias=AliasChoices("LITELLM_HEALTHZ_URL"),
        ),
    ]
    default_chat_model: Annotated[
        str,
        Field(
            default=DEFAULT_CHAT_MODEL,
            description=(
                "Default OpenAI-compatible chat model id for LiteLLM and direct OpenAI; also used when an Azure instance has no ``available_models`` (or empty first segment)."
            ),
            validation_alias=AliasChoices("DEFAULT_CHAT_MODEL"),
            min_length=1,
        ),
    ]

    azure_openai_instance: dict[str, AzureOpenAiInstance] = {}

    def _resolve_postgres_connect(
        self,
        *,
        host: str,
        user: str,
        port: int,
        query: str | None,
    ) -> tuple[str, str, int, str | None]:
        ph, pu, pp, rewritten = supabase_session_pooler_targets(
            host,
            user,
            port,
            pooler_region=self.supabase_pooler_region,
        )
        if rewritten:
            _log.info(
                "Using Supabase session pooler for IPv4 (direct db.*.supabase.co is IPv6-only): host=%s user=%s (was host=%s user=%s)",
                ph,
                pu,
                host.strip(),
                user.strip(),
            )
        ref = resolve_supabase_project_ref(
            explicit=self.supabase_project_ref,
            supabase_url=self.supabase_url,
            db_style_host=host,
        )
        pu_before = pu
        pu = ensure_supavisor_pooler_username(ph, pu, ref)
        if pu == pu_before and is_supabase_supavisor_pooler_host(ph) and pu_before.strip().lower() == "postgres":
            _log.warning(
                "Supabase pooler host %s requires username postgres.<project_ref>, not plain postgres; set SUPABASE_URL, SUPABASE_PROJECT_REF, or POSTGRES_HOST=db.<ref>.supabase.co with SUPABASE_POOLER_REGION.",
                ph,
            )
        q = merge_postgres_query_sslmode_require(query) if is_supabase_postgres_host(ph) else query
        return ph, pu, pp, q

    def build_app_connection_string(self) -> str:
        """Connection URI for runtime pool and ``databases`` (libpq / psycopg)."""
        h, u, p, q = self._resolve_postgres_connect(
            host=self.postgres_host,
            user=self.postgres_user,
            port=self.postgres_port,
            query=self.postgres_query,
        )
        url = make_postgres_url(
            driver=self.postgres_driver,
            username=u,
            password=self.postgres_password.get_secret_value(),
            host=h,
            port=p,
            database=self.postgres_db,
            query=q,
            sqlalchemy_psycopg=False,
        )
        return url.render_as_string(hide_password=False)

    def build_migration_connection_string(self) -> str:
        """SQLAlchemy URL for sync engine and Alembic (postgresql+psycopg when base driver is postgresql)."""
        mh = self.postgres_migration_host or self.postgres_host
        mu = self.postgres_migration_user or self.postgres_user
        mp = self.postgres_migration_port if self.postgres_migration_port is not None else self.postgres_port
        mq = self.postgres_migration_query if self.postgres_migration_query is not None else self.postgres_query
        h, u, p, q = self._resolve_postgres_connect(host=mh, user=mu, port=mp, query=mq)
        url = make_postgres_url(
            driver=self.postgres_driver,
            username=u,
            password=(self.postgres_migration_password.get_secret_value() if self.postgres_migration_password is not None else self.postgres_password.get_secret_value()),
            host=h,
            port=p,
            database=self.postgres_migration_db or self.postgres_db,
            query=q,
            sqlalchemy_psycopg=True,
        )
        return url.render_as_string(hide_password=False)

    @property
    def db_host(self) -> str:
        return self.postgres_host

    @property
    def db_user(self) -> str:
        return self.postgres_user

    @property
    def db_password(self) -> str:
        return self.postgres_password.get_secret_value()

    @property
    def db_name(self) -> str:
        return self.postgres_db

    @property
    def db_port(self) -> int:
        return self.postgres_port

    # s3 settings (all optional — app can start without OVH object storage)
    ovh_username: Annotated[
        Optional[SecretStr],
        BeforeValidator(_unset_empty_env),
        Field(
            default="user-ALBANANDRIEU",
            description="The ovh user's unique username",
        ),
    ]
    ovh_password: Annotated[
        Optional[SecretStr],
        BeforeValidator(_unset_empty_env),
        Field(
            default=None,
            description="OVH password; omit when not using OVH object storage",
        ),
    ]
    ovh_project_name: Annotated[
        Optional[str],
        BeforeValidator(_unset_empty_env),
        Field(
            default=None,
            description="OVH project name; omit when not using OVH object storage",
        ),
    ]
    ovh_container: str = "nabla_models"

    @field_validator("ovh_username", mode="after")
    @classmethod
    def _ovh_username_non_empty_when_set(cls, value: Optional[SecretStr]) -> Optional[SecretStr]:
        if value is not None and not value.get_secret_value().strip():
            msg = "ovh_username, when set, cannot be blank"
            raise ValueError(msg)
        return value

    @field_validator("ovh_password", mode="after")
    @classmethod
    def _ovh_password_min_length_when_set(cls, value: Optional[SecretStr]) -> Optional[SecretStr]:
        if value is not None and len(value.get_secret_value()) < 8:
            msg = "ovh_password, when set, must be at least 8 characters"
            raise ValueError(msg)
        return value

    @field_validator("ovh_project_name", mode="after")
    @classmethod
    def _ovh_project_name_non_empty_when_set(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            msg = "ovh_project_name, when set, cannot be blank"
            raise ValueError(msg)
        return value

    oauth_token_secret: Annotated[SecretStr, Field(min_length=8)]

    keycloak_server_url: Annotated[str, Field(min_length=1)]
    keycloak_realm: Annotated[str, Field(min_length=1)]
    keycloak_client_id: Annotated[str, Field(min_length=1)]
    keycloak_client_secret: Annotated[SecretStr, Field(min_length=8)]

    metrics_enabled: bool = True

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


class APIDeploymentSettings(PrometheusSettings, _Settings):
    # API related
    # api_port: int
    api_log_level: str = "INFO"

    # Scope
    scope: Literal["sample-V1", "sample-V2"] = "sample-V2"

    a2a_enabled: bool = Field(
        default=False,
        description="When true, mount the in-process A2A JSON-RPC app at ``/a2a`` (requires ``a2a-sdk``).",
        validation_alias=AliasChoices("A2A_ENABLED"),
    )


@lru_cache()
def get_settings() -> APIDeploymentSettings:
    """
    Return Settings object as a dependency and use @lru_cache
    decorator to create object and load .env file only once

    :raises: ValidationError
    :return: An instance of APIDeploymentSettings or_Settings
    """

    # Right now we ignore the fact that pyright complains about not
    #  setting default values in the configuration.
    # Thus, we can either set some by default (even dummies) or just
    #  silence pyright
    return APIDeploymentSettings()  # pyright: ignore


keycloak_openid = KeycloakOpenID(
    server_url=get_settings().keycloak_server_url,
    realm_name=get_settings().keycloak_realm,
    client_id=get_settings().keycloak_client_id,
    client_secret_key=get_settings().keycloak_client_secret.get_secret_value(),
)


def get_openid_config():
    return keycloak_openid.well_known()


_unleash_refresh_s = int(os.environ.get("UNLEASH_REFRESH_INTERVAL", "60"))
_unleash_metrics_s = int(os.environ.get("UNLEASH_METRICS_INTERVAL", "90"))
# GitLab SaaS `/client/features` can exceed 15s under load; tune via UNLEASH_REQUEST_TIMEOUT.
_unleash_timeout_s = int(os.environ.get("UNLEASH_REQUEST_TIMEOUT", "45"))
_unleash_retries = int(os.environ.get("UNLEASH_REQUEST_RETRIES", "4"))

if UNLEASH_ENABLED:
    client = UnleashClient(
        url=UNLEASH_API_URL.rstrip("/"),
        app_name=UNLEASH_APP_NAME,
        instance_id=UNLEASH_INSTANCE_ID,
        refresh_interval=_unleash_refresh_s,
        metrics_interval=_unleash_metrics_s,
        request_timeout=_unleash_timeout_s,
        request_retries=_unleash_retries,
        custom_options=_unleash_requests_kwargs(),
        disable_metrics=_env_bool("UNLEASH_DISABLE_METRICS", False),
    )
    client.initialize_client()
else:
    client = None


def is_unleash_feature_enabled(feature_name: str, *, default_when_disabled: bool = False) -> bool:
    """Evaluate a flag only when the Unleash integration is enabled."""
    if not UNLEASH_ENABLED or client is None:
        return default_when_disabled
    return client.is_enabled(feature_name)


# statsig = Statsig(STATSIG_API_KEY)
# statsig.initialize().wait()

# or with StatsigOptions
options = StatsigOptions()
options.environment = "development"

statsig = Statsig(STATSIG_API_KEY, options)
statsig.initialize().wait()

# or with StatsigOptions
options = StatsigOptions()
options.environment = "development"

statsig = Statsig(STATSIG_API_KEY, options)
statsig.initialize().wait()
