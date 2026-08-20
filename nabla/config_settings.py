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
from statsig_python_core import (
    Statsig,
    StatsigOptions,
)
from UnleashClient import UnleashClient

from nabla.version import API_VERSION, RELEASE_VERSION, RUNTIME_VERSION
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
APP_PREFIX_VERSION = API_VERSION
APP_VERSION = RELEASE_VERSION
APP_RUNTIME_VERSION = RUNTIME_VERSION

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
DD_TRACE_AGENT_URL = os.environ.get("DD_TRACE_AGENT_URL", "")
REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")

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
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.lower() in ("true", "1", "yes")


def _configured_secret(value: str) -> bool:
    """Return true only for non-placeholder feature-flag credentials."""
    return bool(value.strip()) and value.strip().upper() not in {"XXX", "CHANGEME", "PLACEHOLDER"}


# --- remainder of settings model ---
