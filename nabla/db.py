from typing import Final

from databases import Database
from ddtrace import patch
from fastapi import Depends
from functools import lru_cache
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from nabla.config_settings import get_settings

# See https://github.com/KenMwaura1/Fast-Api-Grafana-Starter/tree/main


# Database url if none is passed the default one is used
DB_URL: Final[str] = str(get_settings().db_url)

patch(sqlalchemy=True)

# SQLAlchemy
# engine = create_engine(DB_URL)


@lru_cache(maxsize=1)  # Create only 1 engine instance for global reuse
def get_engine():
    return create_async_engine(DB_URL)

async def get_db(engine=Depends(get_engine)):
    async with AsyncSession(engine) as session:
        yield session


# Use a PIN to specify metadata related to this engine
# Pin.override(engine, service="fastapisample")

# metadata = MetaData()
# notes = Table(
#     "notes",
#     metadata,
#     Column("id", Integer, primary_key=True),
#     Column("title", String(50)),
#     Column("description", String(50)),
#     Column("completed", String(8), default="False"),
#     Column(
#         "created_date",
#         String(50),
#         default=dt.now(tz("Europe/Paris")).strftime("%Y-%m-%d %H:%M"),
#     ),
# )

# Databases query builder

database = Database(DB_URL, max_inactive_connection_lifetime=300)
