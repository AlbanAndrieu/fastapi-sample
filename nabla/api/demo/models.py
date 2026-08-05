import dataclasses
import json
import random
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Deque, Dict, List

import orjson
import polars as pl
from pydantic import BaseModel

# With PostgreSQL
from sqlalchemy import Column, DateTime, Float, Integer, String
from sqlalchemy.orm import declarative_base

from nabla.api.db.database import SessionLocal, engine
from nabla.api.demo.socket.redis import (
    REDIS_CHANNEL,
    REDIS_SENSOR_CHANNEL,
    REDIS_TASK_QUEUE,
    redis,
)
from nabla.config_settings import UNLEASH_ENABLED, is_unleash_feature_enabled
from nabla.utils.logger import logger

Base = declarative_base()


async def init_db():
    Base.metadata.create_all(engine)


class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def serialize_dates(v):
    if hasattr(v, "isoformat"):
        return v.isoformat()
    elif isinstance(v, datetime):
        return v.isoformat()
    elif isinstance(v, SensorReading):
        logger.debug(f"SensorReading: {v}")
        return str(v)
    else:
        raise TypeError(
            "Unserializable object {} of type {}".format(v, type(v)),
        )


# Sensor reading model with sqlalchemy
@dataclasses.dataclass
class SensorReading(Base):
    __tablename__ = "sensor_reading"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, nullable=False)
    # timestamp = Column(
    #     "created_date",
    #     String(50),
    #     default=datetime.now(tz("Europe/Paris")).strftime("%Y-%m-%d %H:%M"),
    # )
    temperature = Column(Float, nullable=False)
    humidity = Column(Float, nullable=False)
    pressure = Column(Float, nullable=False)
    status = Column(String, nullable=False)

    def __str__(self):
        return f"SensorReading ID : {self.id}\tTemperature : {self.temperature}\tHumidity : {self.humidity}\tPressure : {self.pressure}\tStatus : {self.status}\tCreated Date : {self.timestamp}"

    def toJSON(self):
        logger.info(f"SensorReading toJSON: {self}")
        return orjson.dumps(self, option=orjson.OPT_SORT_KEYS).decode()
        # return json.dumps(
        #     self,
        #     default=serialize_dates,
        #     sort_keys=True,
        #     indent=4)


# Sensor event model with pydantic validation
@dataclasses.dataclass
class SensorEvent(BaseModel):
    # model_config = ConfigDict(
    #     str_max_length=120,      # hard caps avoid pathological inputs
    #     extra="ignore",          # drop unknown fields instead of raising
    #     revalidate_instances="never",  # don't re-check already-validated data
    #     ser_json_inf_nan=False   # stricter but faster JSON
    # )

    timestamp: str
    temperature: float
    humidity: float
    pressure: float
    status: str

    def __init__(self, timestamp: str = "2021-01-01T00:00:00", temperature: float = 20.0, humidity: float = 50.0, pressure: float = 1013.0, status: str = "normal") -> None:
        super().__init__(timestamp=timestamp, temperature=temperature, humidity=humidity, pressure=pressure, status=status)

    def toJSON(self):
        logger.info(f"SensorEvent toJSON: {self}")
        return json.dumps(
            self,
            default=lambda o: o.__dict__,
            sort_keys=True,
            indent=4,
        )


async def save_redis(suffix, data: Any):
    res = None

    logger.debug(f"Data type: {type(data)}")

    if isinstance(data, str):
        res = await redis.set(
            REDIS_CHANNEL + REDIS_TASK_QUEUE + suffix,
            data,
            ex=120,
        )
    elif isinstance(data, dict):
        res = await redis.set(
            REDIS_CHANNEL + REDIS_TASK_QUEUE + suffix,
            json.dumps(data, default=serialize_dates),
            ex=120,
        )
    # elif isinstance(data, SensorReading):
    #     # TODO : This is not working
    #     res = redis.json().set(
    #         REDIS_CHANNEL + ".task_queue." + suffix,
    #         "$",
    #         data.toJSON(),
    #     )
    else:
        raise ValueError(f"Invalid data type: {type(data)}")

    return res


class SensorData:
    def __init__(self):
        logger.info("Initializing SensorData")

        # Room temperature range (adjust if you live in Antarctica)
        self.min_temp = 18.0
        self.max_temp = 26.0
        self.min_humidity = 30.0
        self.max_humidity = 65.0

        logger.info("Sensor data generator initialized")
        self._initialize_history()

    def _initialize_history(self):
        """Bootstrap with realistic historical data"""
        base_time = datetime.now() - timedelta(minutes=10)
        history = []

        logger.debug("Generating 50 historical sensor readings")
        for i in range(50):
            timestamp = base_time + timedelta(seconds=i * 12)  # Every 12 seconds
            history.append(self.generate_reading(timestamp))

        # Store in deque for efficient updates
        recent_readings.extend(history)
        logger.info(f"Initialized sensor history with {len(history)} readings")

    def generate_reading(self, timestamp: datetime | None = None) -> Dict:
        """Generate a sensor reading with optional timestamp"""
        if timestamp is None:
            # timestamp = datetime.now(tz("Europe/Paris"))
            timestamp = datetime.now()

        reading = {
            "timestamp": timestamp.isoformat(),
            "temperature": round(random.uniform(self.min_temp, self.max_temp), 1),  # noqa: S311 # nosec
            "humidity": round(random.uniform(self.min_humidity, self.max_humidity), 1),  # noqa: S311 # nosec
            "pressure": round(random.uniform(1000, 1030), 1),  # noqa: S311 # nosec
            "status": random.choice(["normal", "warning", "critical"]),  # noqa: S311 # nosec
        }

        logger.debug("Sensor reading created successfully")
        # Log critical readings for monitoring
        if reading["status"] == "critical":
            logger.debug(
                f"Critical sensor reading: temp={reading['temperature']}°C, humidity={reading['humidity']}%, pressure={reading['pressure']}hPa",
            )

        return reading

    async def save_reading_to_redis(self, data: Dict[str, Any]) -> None:
        logger.debug(f"SensorData toJSON: {self}")

        # TODO push list of readings to redis
        # redis.lpush(REDIS_CHANNEL, db_reading.to_json())
        # redis.lpush(REDIS_CHANNEL + ".task_queue_lpush", orjson.dumps(data, option=orjson.OPT_SORT_KEYS))

        # res = await set_cache("temperature", db_reading.temperature)
        # print(res)
        # OK res = await set_cache("data", str(db_reading))
        # NOK res = await set_cache("data", db_reading)

        if is_unleash_feature_enabled("sensor_reading_redis_cache"):
            # TODO : Below is working, BUT it is not a good idea to push the whole reading to the cache
            # because it is too big and it is slowing down the system
            res = await save_redis(REDIS_SENSOR_CHANNEL, data)
            logger.debug(f"queued data: {res}")
            return res
        elif UNLEASH_ENABLED:
            logger.warning("Feature flag : sensor_reading_redis_cache is not enabled")
        return None

    async def save_reading(self, data: Dict[str, Any]) -> None:
        """Save sensor reading to PostgreSQL database"""
        await self.save_reading_to_db(data)
        """Save sensor reading to Redis"""
        await self.save_reading_to_redis(data)

    # session: Session = Depends(get_session)
    async def save_reading_to_db(self, data: Dict[str, Any]) -> None:
        """Save sensor reading to PostgreSQL database"""

        session = SessionLocal()
        try:
            # Convert ISO string back to datetime object
            timestamp = datetime.fromisoformat(data["timestamp"])

            db_reading = SensorReading(
                timestamp=timestamp,
                temperature=data["temperature"],
                humidity=data["humidity"],
                pressure=data["pressure"],
                status=data["status"],
            )

            logger.debug(f"db_reading: {db_reading.toJSON()}")

            session.add(db_reading)
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            # session.aclose()
            session.close()


def get_sensor_dataframe() -> pl.DataFrame:
    """Convert readings to Polars DataFrame for easy manipulation"""
    if not recent_readings:
        logger.warning("No sensor readings available for DataFrame conversion")
        return pl.DataFrame()

    logger.debug(f"Converting {len(recent_readings)} readings to Polars DataFrame")

    # Polars DataFrame creation is lightning fast
    df = pl.DataFrame(list(recent_readings))

    # Parse timestamps (Polars handles this beautifully)
    df = df.with_columns(
        [pl.col("timestamp").str.strptime(pl.Datetime, format="%Y-%m-%dT%H:%M:%S.%f")],
    )
    #  [pl.col("timestamp").str.strptime(pl.Datetime, format="%d/%B/%Y %H:%M:%S")]

    logger.debug(f"Created DataFrame with {len(df)} rows and {len(df.columns)} columns")
    return df


def get_statistical_summary() -> Dict:
    """Calculate statistics using Polars (because it's blazing fast)"""
    df = get_sensor_dataframe()

    if df.is_empty():
        logger.warning("Cannot calculate statistics: empty DataFrame")
        return {}

    logger.debug("Calculating statistical summary")

    # Polars makes complex aggregations simple
    stats = df.select(
        [
            pl.col("temperature").mean().alias("temp_mean"),
            pl.col("temperature").std().alias("temp_std"),
            pl.col("humidity").mean().alias("humidity_mean"),
            pl.col("humidity").std().alias("humidity_std"),
            pl.col("pressure").mean().alias("pressure_mean"),
            pl.col("pressure").std().alias("pressure_std"),
            pl.col("status").value_counts().alias("status_counts"),
        ],
    ).to_dict(as_series=False)

    logger.info("Statistical summary calculated successfully")
    return stats


def detect_anomalies() -> List[Dict]:
    """Detect outliers using statistical methods (Polars style)"""
    df = get_sensor_dataframe()

    if len(df) < 10:  # Need enough data for meaningful stats
        logger.debug(
            "Insufficient data for anomaly detection (need at least 10 readings)",
        )
        return []

    logger.debug("Running anomaly detection using z-score method")

    # Calculate z-scores for temperature (Polars vectorized operations)
    df_with_zscore = df.with_columns(
        [
            ((pl.col("temperature") - pl.col("temperature").mean()) / pl.col("temperature").std()).alias("temp_zscore"),
        ],
    )

    # Find outliers (|z-score| > 2)
    anomalies = df_with_zscore.filter(pl.col("temp_zscore").abs() > 2).select(["timestamp", "temperature", "temp_zscore"]).to_dicts()

    if anomalies:
        logger.warning(f"Detected {len(anomalies)} temperature anomalies")
        for anomaly in anomalies:
            logger.warning(
                f"Anomaly: {anomaly['temperature']}°C at {anomaly['timestamp']} (z-score: {anomaly['temp_zscore']:.2f})",
            )
    else:
        logger.debug("No temperature anomalies detected")

    return anomalies


# Store the last 100 readings (more data = better Plotly charts)
recent_readings: Deque[Dict[str, Any]] = deque(maxlen=100)
