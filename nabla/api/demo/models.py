import dataclasses
import json
import random
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Deque, Dict, Final, List

import orjson
import plotly.graph_objects as go
import polars as pl
from ddtrace import patch
from pydantic import BaseModel

# With PostgreSQL
from sqlalchemy import Column, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from nabla.api.demo.ws.event_bus import REDIS_CHANNEL, redis
from nabla.config_settings import get_settings
from nabla.utils.logger import logger

# from rq import Queue



Base = declarative_base()

# Database url if none is passed the default one is used
DB_URL: Final[str] = str(get_settings().db_url)

patch(sqlalchemy=True)

def orjson_serializer(obj):
    """
        Note that `orjson.dumps()` return byte array, while sqlalchemy expects string, thus `decode()` call.
    """
    return orjson.dumps(obj, option=orjson.OPT_SERIALIZE_NUMPY | orjson.OPT_NAIVE_UTC).decode()


# SQLAlchemy
engine = create_engine(DB_URL, json_serializer=orjson_serializer,
    json_deserializer=orjson.loads)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)



def serialize_dates(v):
    if hasattr(v, 'isoformat'):
        return v.isoformat()
    elif isinstance(v, datetime):
        return v.isoformat()
    elif isinstance(v, SensorReading):
      logger.debug(f"SensorReading: {v}")
      return str(v)
    else:
        raise TypeError(
            "Unserializable object {} of type {}".format(v, type(v))
        )

# Sensor reading model with sqlalchemy
@dataclasses.dataclass
class SensorReading(Base):
    __tablename__ = "sensor_readings"

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
       return f"Sensor ID : {self.id}\tTemperature : {self.temperature}\tHumidity : {self.humidity}\tPressure : {self.pressure}\tStatus : {self.status}\tCreated Date : {self.timestamp}"

    def toJSON(self):
        logger.info(f"toJSON: {self}")
        return json.dumps(
            self,
            #default=lambda o: o.__dict__,
            # cls=DateTimeEncoder,
            default=serialize_dates,
            sort_keys=True,
            indent=4)



# Sensor event model with pydantic validation
@dataclasses.dataclass
class SensorEvent(BaseModel):
    timestamp: str
    temperature: float
    humidity: float
    pressure: float
    status: str

    def __init__(self, timestamp: str = "2021-01-01T00:00:00", temperature: float = 20.0, humidity: float = 50.0, pressure: float = 1013.0, status: str = "normal") -> None:
        super().__init__(timestamp=timestamp, temperature=temperature, humidity=humidity, pressure=pressure, status=status)



async def set_cache(suffix, data: Any):
    res = None

    logger.debug(f"Data type: {type(data)}")

    if isinstance(data, str):
        res =await redis.set(
            REDIS_CHANNEL + ".task_queue." + suffix,
            data,
            ex=120,
        )
    elif isinstance(data, dict):
       res = await redis.set(
            REDIS_CHANNEL + ".task_queue." + suffix,
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

    def generate_reading(self, timestamp: datetime = None) -> Dict:
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

        logger.info("Sensor reading created successfully")
        # Log critical readings for monitoring
        if reading["status"] == "critical":
            logger.warning(
                f"Critical sensor reading: temp={reading['temperature']}°C, "
                f"humidity={reading['humidity']}%, pressure={reading['pressure']}hPa"
            )

        return reading


    # TODO @cache(expire=60, coder=ORJsonCoder)
    async def save_reading(self, data: Dict[str, Any]) -> None:
        """Save sensor reading to PostgreSQL database"""
        db = SessionLocal()

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

            # redis.lpush(REDIS_CHANNEL, str(db_reading))
            # redis.lpush(REDIS_CHANNEL, db_reading.to_json())
            redis.lpush(REDIS_CHANNEL + ".task_queue_lpush", orjson.dumps(data, option=orjson.OPT_SORT_KEYS))

            # res = await set_cache("temperature", db_reading.temperature)
            # print(res)
            # OK res = await set_cache("data", str(db_reading))
            # NOK res = await set_cache("data", db_reading)
            res = await set_cache("data", data)
            logger.debug(f"queued data: {res}")

            db.add(db_reading)
            db.commit()
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    def create_status_distribution(self, df: pl.DataFrame) -> str:
        """Create status distribution pie chart"""
        if df.is_empty():
            logger.warning("Cannot create status chart: empty DataFrame")
            return self._create_empty_chart("No status data")

        # Get status counts using Polars
        status_counts = df["status"].value_counts().sort("status")

        logger.debug(
            f"Status distribution: {dict(zip(status_counts['status'].to_list(), status_counts['count'].to_list(), strict=False))}"
        )

        fig = go.Figure(
            data=[
                go.Pie(
                    labels=status_counts["status"].to_list(),
                    values=status_counts["count"].to_list(),
                    marker_colors=[
                        self.colors.get(status, "#6B7280")
                        for status in status_counts["status"].to_list()
                    ],
                    hovertemplate="<b>%{label}</b><br>Count: %{value}<br>Percentage: %{percent}<extra></extra>",
                    textinfo="label+percent",
                )
            ]
        )

        fig.update_layout(
            **self.layout_defaults,  # pyright: ignore[reportAttributeAccessIssue]
            title="Sensor Status Distribution",
            # height=300
        )

        logger.info("Status distribution chart created successfully")
        return fig.to_html(include_plotlyjs="cdn", div_id="status-chart")

    def create_correlation_heatmap(self, df: pl.DataFrame) -> str:
        """Create correlation heatmap between metrics"""
        if df.is_empty() or len(df) < 2:
            logger.warning("Cannot create correlation heatmap: insufficient data")
            return self._create_empty_chart("Insufficient data for correlation")

        logger.debug("Calculating correlation matrix")

        # Calculate correlation matrix using Polars
        numeric_cols = ["temperature", "humidity", "pressure"]
        corr_data = []

        for col1 in numeric_cols:
            row = []
            for col2 in numeric_cols:
                if col1 == col2:
                    correlation = 1.0
                else:
                    # Calculate Pearson correlation
                    correlation = df.select(pl.corr(col1, col2)).item()
                    if correlation is None:  # Handle NaN correlations
                        correlation = 0.0
                row.append(correlation)
            corr_data.append(row)

        logger.debug(f"Correlation matrix calculated: {corr_data}")

        fig = go.Figure(
            data=go.Heatmap(
                z=corr_data,
                x=numeric_cols,
                y=numeric_cols,
                colorscale="RdBu",
                zmid=0,
                text=[[f"{val:.2f}" for val in row] for row in corr_data],
                texttemplate="%{text}",
                textfont={"size": 12},
                hovertemplate="<b>%{y} vs %{x}</b><br>Correlation: %{z:.3f}<extra></extra>",
            )
        )

        fig.update_layout(
            **self.layout_defaults,  # pyright: ignore[reportAttributeAccessIssue]
            title="Sensor Correlation Matrix",
            # height=300
        )

        logger.info("Correlation heatmap created successfully")
        return fig.to_html(include_plotlyjs="cdn", div_id="correlation-chart")

    def create_anomaly_highlights(self, df: pl.DataFrame, anomalies: List[Dict]) -> str:
        """Create chart highlighting anomalous readings"""
        if df.is_empty():
            logger.warning("Cannot create anomaly chart: empty DataFrame")
            return self._create_empty_chart("No data for anomaly detection")

        logger.debug(f"Creating anomaly chart with {len(anomalies)} anomalies")

        timestamps = df["timestamp"].to_list()
        temperatures = df["temperature"].to_list()

        fig = go.Figure()

        # Normal temperature line
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=temperatures,
                mode="lines+markers",
                name="Temperature",
                line={"color": self.colors["temperature"]},
                marker={"size": 4},
            )
        )

        # Highlight anomalies
        if anomalies:
            anomaly_times = [datetime.fromisoformat(a["timestamp"]) for a in anomalies]
            anomaly_temps = [a["temperature"] for a in anomalies]

            logger.info(f"Highlighting {len(anomalies)} anomalies on chart")

            fig.add_trace(
                go.Scatter(
                    x=anomaly_times,
                    y=anomaly_temps,
                    mode="markers",
                    name="Anomalies",
                    marker={
                        "color": self.colors["critical"], "size": 10, "symbol": "diamond"
                    },
                    hovertemplate="<b>Anomaly Detected</b><br>Temperature: %{y:.1f}°C<br>%{x}<extra></extra>",
                )
            )

        fig.update_layout(
            **self.layout_defaults,  # pyright: ignore[reportAttributeAccessIssue]
            title="Temperature with Anomaly Detection",
            # height=300,
            xaxis_title="Time",
            yaxis_title="Temperature (°C)",
        )

        logger.info("Anomaly detection chart created successfully")
        return fig.to_html(include_plotlyjs="cdn", div_id="anomaly-chart")

    def _create_empty_chart(self, message: str) -> str:
        """Create placeholder chart for empty data"""
        logger.debug(f"Creating empty chart placeholder: {message}")

        fig = go.Figure()
        fig.add_annotation(
            text=message,
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            xanchor="center",
            yanchor="middle",
            font={"size": 16, "color": "gray"},
        )
        fig.update_layout(
            **self.layout_defaults,  # pyright: ignore[reportAttributeAccessIssue]
            # height=300,
            xaxis={"visible": False},
            yaxis={"visible": False},
        )
        return fig.to_html(include_plotlyjs="cdn")


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
        [pl.col("timestamp").str.strptime(pl.Datetime, format="%Y-%m-%dT%H:%M:%S.%f")]
    )

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
        ]
    ).to_dict(as_series=False)

    logger.info("Statistical summary calculated successfully")
    return stats


def detect_anomalies() -> List[Dict]:
    """Detect outliers using statistical methods (Polars style)"""
    df = get_sensor_dataframe()

    if len(df) < 10:  # Need enough data for meaningful stats
        logger.debug(
            "Insufficient data for anomaly detection (need at least 10 readings)"
        )
        return []

    logger.debug("Running anomaly detection using z-score method")

    # Calculate z-scores for temperature (Polars vectorized operations)
    df_with_zscore = df.with_columns(
        [
            (
                (pl.col("temperature") - pl.col("temperature").mean())
                / pl.col("temperature").std()
            ).alias("temp_zscore")
        ]
    )

    # Find outliers (|z-score| > 2)
    anomalies = (
        df_with_zscore.filter(pl.col("temp_zscore").abs() > 2)
        .select(["timestamp", "temperature", "temp_zscore"])
        .to_dicts()
    )

    if anomalies:
        logger.warning(f"Detected {len(anomalies)} temperature anomalies")
        for anomaly in anomalies:
            logger.warning(
                f"Anomaly: {anomaly['temperature']}°C at {anomaly['timestamp']} "
                f"(z-score: {anomaly['temp_zscore']:.2f})"
            )
    else:
        logger.debug("No temperature anomalies detected")

    return anomalies


# Store the last 100 readings (more data = better Plotly charts)
recent_readings: Deque[Dict[str, Any]] = deque(maxlen=100)

# Create a queue object with the connection
# task_queue = Queue('low', connection=redis)

# Create tables
Base.metadata.create_all(bind=engine)
# Base.metadata.create_all(bind=get_engine())
