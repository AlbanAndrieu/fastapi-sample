"""Settings for nabla project"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, ClassVar, Literal, Optional

from keycloak import KeycloakOpenID
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    keycloak_server_url: Annotated[str, Field(min_length=1)]
    keycloak_server_url: Annotated[str, Field(min_length=1)]
    keycloak_realm: Annotated[str, Field(min_length=1)]
    keycloak_client_id: Annotated[str, Field(min_length=1)]
    keycloak_client_secret: Annotated[str, Field(min_length=1)]

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


@lru_cache()
def get_settings() -> _Settings:
    """
    Return Settings object as a dependency and use @lru_cache
    decorator to create object and load .env file only once

    :raises: ValidationError
    :return: An instance of _Settings
    """

    # Right now we ignore the fact that pyright complains about not
    #  setting default values in the configuration.
    # Thus, we can either set some by default (even dummies) or just
    #  silence pyright
    return _Settings()  # pyright: ignore


keycloak_openid = KeycloakOpenID(
    server_url=get_settings().keycloak_server_url,
    realm_name=get_settings().keycloak_realm,
    client_id=get_settings().keycloak_client_id,
    client_secret_key=get_settings().keycloak_client_secret,
)


def get_openid_config():
    return keycloak_openid.well_known()
