"""PostgreSQL and Supabase settings domain."""

import logging
from typing import Annotated, Optional

from pydantic import AliasChoices, BeforeValidator, Field, SecretStr

from nabla.db_config import (
    ensure_supavisor_pooler_username,
    is_supabase_postgres_host,
    is_supabase_supavisor_pooler_host,
    make_postgres_url,
    merge_postgres_query_sslmode_require,
    resolve_supabase_project_ref,
    supabase_session_pooler_targets,
)
from nabla.settings.base import SettingsBase, unset_empty_env

_log = logging.getLogger(__name__)


class DatabaseSettings(SettingsBase):
    """PostgreSQL and Supabase connection settings."""

    postgres_driver: Annotated[
        str,
        Field(
            default="postgresql",
            description="SQLAlchemy/libpq driver prefix.",
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
    ] = SecretStr("backpass")  # nosec B105 -- development default only
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
            description="Optional database URI query.",
            validation_alias=AliasChoices("POSTGRES_QUERY"),
        ),
    ]

    postgres_migration_host: Annotated[
        Optional[str],
        Field(default=None, validation_alias=AliasChoices("POSTGRES_MIGRATION_HOST")),
    ]
    postgres_migration_port: Annotated[
        Optional[int],
        Field(default=None, validation_alias=AliasChoices("POSTGRES_MIGRATION_PORT")),
    ]
    postgres_migration_user: Annotated[
        Optional[str],
        Field(default=None, validation_alias=AliasChoices("POSTGRES_MIGRATION_USER")),
    ]
    postgres_migration_password: Annotated[
        Optional[SecretStr],
        Field(default=None, validation_alias=AliasChoices("POSTGRES_MIGRATION_PASSWORD")),
    ]
    postgres_migration_db: Annotated[
        Optional[str],
        Field(default=None, validation_alias=AliasChoices("POSTGRES_MIGRATION_DB")),
    ]
    postgres_migration_query: Annotated[
        Optional[str],
        Field(default=None, validation_alias=AliasChoices("POSTGRES_MIGRATION_QUERY")),
    ]

    supabase_pooler_region: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Supavisor session-pooler region.",
            validation_alias=AliasChoices("SUPABASE_POOLER_REGION"),
        ),
    ]
    supabase_project_ref: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Supabase project ref used by pooler usernames.",
            validation_alias=AliasChoices("SUPABASE_PROJECT_REF", "SUPABASE_PROJECT_ID"),
        ),
    ]
    supabase_url: Annotated[
        Optional[str],
        Field(default=None, validation_alias=AliasChoices("SUPABASE_URL")),
    ]
    supabase_service_role_key: Annotated[
        Optional[SecretStr],
        Field(default=None, validation_alias=AliasChoices("SUPABASE_SERVICE_ROLE_KEY")),
    ]
    supabase_publishable_key: Annotated[
        Optional[SecretStr],
        BeforeValidator(unset_empty_env),
        Field(
            default=None,
            validation_alias=AliasChoices("SUPABASE_PUBLISHABLE_KEY", "SUPABASE_KEY"),
        ),
    ]
    supabase_health_table: Annotated[
        str,
        Field(
            default="note",
            pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
            validation_alias=AliasChoices("SUPABASE_HEALTH_TABLE"),
        ),
    ]

    def _resolve_postgres_connect(
        self,
        *,
        host: str,
        user: str,
        port: int,
        query: str | None,
    ) -> tuple[str, str, int, str | None]:
        resolved_host, resolved_user, resolved_port, rewritten = supabase_session_pooler_targets(
            host,
            user,
            port,
            pooler_region=self.supabase_pooler_region,
        )
        if rewritten:
            _log.info(
                "Using Supabase session pooler for IPv4: host=%s user=%s (was host=%s user=%s)",
                resolved_host,
                resolved_user,
                host.strip(),
                user.strip(),
            )
        project_ref = resolve_supabase_project_ref(
            explicit=self.supabase_project_ref,
            supabase_url=self.supabase_url,
            db_style_host=host,
        )
        previous_user = resolved_user
        resolved_user = ensure_supavisor_pooler_username(
            resolved_host,
            resolved_user,
            project_ref,
        )
        if resolved_user == previous_user and is_supabase_supavisor_pooler_host(resolved_host) and previous_user.strip().lower() == "postgres":
            _log.warning(
                "Supabase pooler host %s requires username postgres.<project_ref>; set SUPABASE_URL, SUPABASE_PROJECT_REF, or a db.<ref>.supabase.co host.",
                resolved_host,
            )
        resolved_query = merge_postgres_query_sslmode_require(query) if is_supabase_postgres_host(resolved_host) else query
        return resolved_host, resolved_user, resolved_port, resolved_query

    def build_app_connection_string(self) -> str:
        """Return the runtime PostgreSQL connection URI."""
        host, user, port, query = self._resolve_postgres_connect(
            host=self.postgres_host,
            user=self.postgres_user,
            port=self.postgres_port,
            query=self.postgres_query,
        )
        url = make_postgres_url(
            driver=self.postgres_driver,
            username=user,
            password=self.postgres_password.get_secret_value(),
            host=host,
            port=port,
            database=self.postgres_db,
            query=query,
            sqlalchemy_psycopg=False,
        )
        return url.render_as_string(hide_password=False)

    def build_migration_connection_string(self) -> str:
        """Return the sync/Alembic PostgreSQL connection URI."""
        migration_host = self.postgres_migration_host or self.postgres_host
        migration_user = self.postgres_migration_user or self.postgres_user
        migration_port = self.postgres_migration_port if self.postgres_migration_port is not None else self.postgres_port
        migration_query = self.postgres_migration_query if self.postgres_migration_query is not None else self.postgres_query
        host, user, port, query = self._resolve_postgres_connect(
            host=migration_host,
            user=migration_user,
            port=migration_port,
            query=migration_query,
        )
        password = self.postgres_migration_password.get_secret_value() if self.postgres_migration_password is not None else self.postgres_password.get_secret_value()
        url = make_postgres_url(
            driver=self.postgres_driver,
            username=user,
            password=password,
            host=host,
            port=port,
            database=self.postgres_migration_db or self.postgres_db,
            query=query,
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
