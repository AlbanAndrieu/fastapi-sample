"""Settings for nabla project"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, ClassVar, Literal, Optional

from keycloak import KeycloakOpenID
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from nabla._version import get_versions
from nabla.utils.prometheus import PrometheusSettings

APP_NAME = os.environ.get("APP_NAME", "fastapi-sample")
APP_PREFIX_VERSION = os.environ.get("APP_PREFIX_VERSION", "v")
APP_VERSION = get_versions()["version"]

EXPOSE_HOST = os.environ.get("EXPOSE_HOST", "0.0.0.0")  # noqa: S104 noqa:B104 # nosec B104
EXPOSE_PORT = int(os.environ.get("EXPOSE_PORT", "8080"))
EXPOSE_MCP_PORT = int(os.environ.get("EXPOSE_MCP_PORT", "8001"))
PYROSCOPE_ENDPOINT = os.environ.get("PYROSCOPE_ENDPOINT", "http://localhost:4040")

DD_AGENT_HOST = os.environ.get("DD_AGENT_HOST", "127.0.0.1")
DD_TRACE_AGENT_PORT = os.environ.get("DD_TRACE_AGENT_PORT", "8126")

REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))  # [invalid-envvar-default]

# http://grpc.jaeger-collector-grpc.service.gra.dev.consul
# http://jaeger-collector-grpc.service.gra.dev.consul:14250
# http://datadog-agent.service.gra.dev.consul:4317
# http://otel-collector.service.gra.dev.consul:9411/api/v2/spans

OTLP_GRPC_ENDPOINT = os.environ.get(
    # "OTLP_GRPC_ENDPOINT", "http://grpc.jaeger-collector-grpc.service.gra.dev.consul"
    "OTLP_GRPC_ENDPOINT",
    "http://datadog-agent.service.gra.dev.consul:4317",
)

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
    "https://11c5d815632831d3274c830441885207@o4505783360356352.ingest.sentry.io/4505783364681728",
)


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
    api_key: Annotated[str, Field(min_length=1)]
    api_alias: Annotated[str, Field(min_length=1)]
    available_models: Annotated[str, Field(min_length=1)]


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

    # db settings
    db_host: Annotated[
        str,
        Field(default="localhost", description="The database host", min_length=1),
    ]
    db_name: Annotated[
        str,
        Field(default="back", description="The database name", min_length=1),
    ]
    db_user: Annotated[
        str,
        Field(default="back", description="The database user", min_length=1),
    ]
    db_password: Annotated[
        str,
        Field(default="back", description="The database password", min_length=1),
    ]
    db_port: int = 5432

    db_url: Optional[str] = (
        "postgresql://fastapisample:password-reset-XXX@127.0.0.1:5432/fastapi_sample_dev"  # nosec
    )

    azure_openai_instance: dict[str, AzureOpenAiInstance] = {}

    # s3 settings
    ovh_username: Annotated[
        str,
        Field(
            default="localhost",
            description="The ovh user's unique username",
            min_length=1,
        ),
    ]
    ovh_password: str = "password"  # noqa: S105
    ovh_project_name: str = Annotated[
        str,
        Field(
            alias="123456789",
            default="123456789",
            description="The ovh user's unique project name",
            min_length=1,
        ),
    ]
    ovh_container: str = "nabla_models"

    oauth_token_secret: str = "my_dev_secret"

    keycloak_server_url: Annotated[str, Field(min_length=1)]
    keycloak_realm: Annotated[str, Field(min_length=1)]
    keycloak_client_id: Annotated[str, Field(min_length=1)]
    keycloak_client_secret: Annotated[str, Field(min_length=1)]

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


class APIDeploymentSettings(PrometheusSettings, _Settings):
    # API related
    # api_port: int
    api_log_level: str = "info"

    # Scope
    scope: Literal["sample-V1", "sample-V2"] = "sample-V2"


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
    client_secret_key=get_settings().keycloak_client_secret,
)


def get_openid_config():
    return keycloak_openid.well_known()
