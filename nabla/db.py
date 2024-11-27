from datetime import datetime as dt

from typing import Final
from databases import Database
from pytz import timezone as tz
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine

from nabla.config_settings import get_settings

# See https://github.com/KenMwaura1/Fast-Api-Grafana-Starter/tree/main


# Database url if none is passed the default one is used
DATABASE_URL: Final[str] = str(get_settings().db_url)

# SQLAlchemy
engine = create_engine(DATABASE_URL)
metadata = MetaData()
notes = Table(
    "notes",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("title", String(50)),
    Column("description", String(50)),
    Column("completed", String(8), default="False"),
    Column(
        "created_date",
        String(50),
        default=dt.now(tz("Africa/Nairobi")).strftime("%Y-%m-%d %H:%M"),
    ),
)
# Databases query builder

database = Database(DATABASE_URL)
