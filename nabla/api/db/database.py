import os
from functools import lru_cache
from typing import Annotated, AsyncGenerator, Final

import orjson
import psycopg_pool
from databases import Database
from ddtrace import patch
from fastapi import Depends
from sqlalchemy import Engine, create_engine

# With PostgreSQL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlmodel import Session as SQLModelSession

from nabla.config_settings import get_settings
from nabla.utils.logger import logger

_settings = get_settings()
# Runtime: app URL from POSTGRES_* (e.g. Supabase pooler). Migrations: build_migration_connection_string().
DB_URL: Final[str] = _settings.build_app_connection_string()
MIGRATION_DB_URL: Final[str] = _settings.build_migration_connection_string()

logger.info("🛢️ Postgres configuration")
logger.info(
    "Postgres app host=%s db=%s (migration host=%s)",
    _settings.postgres_host,
    _settings.postgres_db,
    _settings.postgres_migration_host or _settings.postgres_host,
)
logger.debug("Postgres driver=%s", _settings.postgres_driver)

# TODO: exemple of password to detect
# Below is a security leak on purpose to detect if the password is in the logs
logger.info(f"Postgres URL: {DB_URL}")
logger.info("Postgres URL MIGRATION: %s", MIGRATION_DB_URL)
logger.info(f"Postgres pass: {os.getenv('POSTGRES_PASSWORD')}")
logger.info(f"Postgres driver: {os.getenv('POSTGRES_DRIVER')}")

patch(sqlalchemy=True)


def orjson_serializer(obj):
    """
    Note that `orjson.dumps()` return byte array, while sqlalchemy expects string, thus `decode()` call.
    """
    return orjson.dumps(obj, option=orjson.OPT_SERIALIZE_NUMPY | orjson.OPT_NAIVE_UTC).decode()


# Create a psycopg_pool connection pool
db_pool = psycopg_pool.ConnectionPool(
    # conninfo=DB_URL.render_as_string(True),
    conninfo=DB_URL,
    min_size=0,
    max_size=1,
    max_idle=5,
)

# db_async_pool = psycopg_pool.AsyncConnectionPool(
#     conninfo=DB_URL,
#     min_size=0,
#     max_size=1,
#     max_idle=5,
# )

# @lru_cache(maxsize=1)  # Create only 1 engine instance for global reuse
# def get_async_engine() -> AsyncEngine:
#     # Create a SQLAlchemy engine that uses the psycopg_pool connection pool
#     return create_async_engine(
#         url=DB_URL,
#         poolclass=sqlalchemy.pool.NullPool,  # disable SQLAlchemy's default connection pool
#         creator=db_async_pool.getconn,              # Use Psycopg 3 psycopg_pool to create connections
#         json_serializer=orjson_serializer,
#         json_deserializer=orjson.loads,
#     )


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    # Create a SQLAlchemy engine without connection pool
    # Used by pytest
    # Sync engine uses migration URL (direct session when POSTGRES_MIGRATION_* set).
    return create_engine(
        url=MIGRATION_DB_URL,
        json_serializer=orjson_serializer,
        json_deserializer=orjson.loads,
    )


async def get_db(engine: Annotated[Engine, Depends(get_engine)]):
    async with AsyncSession(engine) as session:
        yield session


# SQLAlchemy
engine = get_engine()

Base = declarative_base()


# Register a 'checkin' event listener to return connections to psycopg_pool
# (https://docs.sqlalchemy.org/en/20/core/events.html#sqlalchemy.events.PoolEvents.checkin)
async def return_to_pool(dbapi_connection, connection_record):
    await db_pool.putconn(dbapi_connection)


async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def init_db():
    # await create_db_and_tables()
    # SQLModel.metadata.create_all(engine)
    Base.metadata.create_all(engine)

    # from nabla.api.demo.models import Base as DemoBase
    # from nabla.api.notes.models import Base as NoteBase
    # from nabla.api.users.models import Base as UserBase
    # UserBase.metadata.create_all(engine)
    # NoteBase.metadata.create_all(engine)
    # DemoBase.metadata.create_all(engine)

    # with engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.drop_all)
    #     await conn.run_sync(Base.metadata.create_all)


# Fix AttributeError: 'Session' object has no attribute 'exec'
# https://github.com/fastapi/sqlmodel/issues/75
SessionLocal = sessionmaker(class_=SQLModelSession, autocommit=False, autoflush=False, bind=engine)
AsyncSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine)
SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# TODO replace get_session with get_async_session
async def get_session() -> None:
    with SessionLocal() as session:
        yield session
    # async with Session(engine, expire_on_commit=False) as session:
    #    yield session


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


# Databases query builder

# database = Database(DB_URL.replace("+psycopg", "").replace("+asyncpg", ""), max_inactive_connection_lifetime=300)
database = Database(DB_URL, max_inactive_connection_lifetime=300)
