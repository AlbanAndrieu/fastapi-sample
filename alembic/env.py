from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context
from nabla.config_settings import get_settings

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
# Skipped when the caller provides its own connection (tests) so the
# embedding process keeps its logging configuration.
if config.config_file_name is not None and "connection" not in config.attributes:
    fileConfig(config.config_file_name)

# URL from POSTGRES_* / POSTGRES_MIGRATION_* (same as sync SQLAlchemy engine).
config.set_main_option("sqlalchemy.url", get_settings().build_migration_connection_string())

from nabla.api.db.metadata import application_metadata  # noqa: E402 — after config so URL is set first

# Every application table (user, note, sensor_reading) for autogenerate and
# schema comparison; the users metadata alone hid ``note`` from Alembic.
target_metadata = application_metadata()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    A caller may pass an open connection through
    ``config.attributes["connection"]`` (Alembic cookbook pattern); the
    PostgreSQL integration tests use it to target a disposable database.
    """
    provided = config.attributes.get("connection")
    if provided is not None:
        context.configure(connection=provided, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return

    connectable = create_engine(
        get_settings().build_migration_connection_string(),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
