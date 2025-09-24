from functools import lru_cache
from typing import AsyncGenerator, Final

import orjson
import psycopg_pool
import sqlalchemy
from databases import Database
from ddtrace import patch
from fastapi import Depends

# With PostgreSQL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

from nabla.config_settings import get_settings

# Database url if none is passed the default one is used
DB_URL: Final[str] = str(get_settings().db_url)

patch(sqlalchemy=True)

def orjson_serializer(obj):
    """
        Note that `orjson.dumps()` return byte array, while sqlalchemy expects string, thus `decode()` call.
    """
    return orjson.dumps(obj, option=orjson.OPT_SERIALIZE_NUMPY | orjson.OPT_NAIVE_UTC).decode()

# Create a psycopg_pool connection pool
mypool = psycopg_pool.ConnectionPool(
    conninfo=DB_URL.replace("+psycopg", ""),
    min_size=0,
    max_size=1,
    max_idle=5,
)

@lru_cache(maxsize=1)  # Create only 1 engine instance for global reuse
def get_engine() -> AsyncEngine:
    # Create a SQLAlchemy engine that uses the psycopg_pool connection pool
    return create_async_engine(
        url=DB_URL,
        poolclass=sqlalchemy.pool.NullPool,  # disable SQLAlchemy's default connection pool
        creator=mypool.getconn,              # Use Psycopg 3 psycopg_pool to create connections
        json_serializer=orjson_serializer,
        json_deserializer=orjson.loads,
    )

async def get_db(engine=Depends(get_engine)):
    async with AsyncSession(engine) as session:
        yield session


# SQLAlchemy
engine = get_engine()

Base = declarative_base()

# Register a 'checkin' event listener to return connections to psycopg_pool
# (https://docs.sqlalchemy.org/en/20/core/events.html#sqlalchemy.events.PoolEvents.checkin)
def return_to_pool(dbapi_connection, connection_record):
    mypool.putconn(dbapi_connection)

# TODO replace get_session with get_async_session
async def get_session() -> AsyncSession:
    async with AsyncSession(engine) as session:
       yield session

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session

async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def init_db():
    await create_db_and_tables()
    # SQLModel.metadata.create_all(engine)
    # Base.metadata.create_all(engine)
    # with engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.drop_all)
    #     await conn.run_sync(Base.metadata.create_all)

SessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Databases query builder

database = Database(DB_URL, max_inactive_connection_lifetime=300)
