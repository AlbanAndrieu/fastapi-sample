import random
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, Final

from ddtrace import patch

# With PostgreSQL
from sqlalchemy import Column, DateTime, Float, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from nabla.config_settings import get_settings

Base = declarative_base()

# Database url if none is passed the default one is used
DB_URL: Final[str] = str(get_settings().db_url)

patch(sqlalchemy=True)

# SQLAlchemy
engine = create_engine(DB_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, nullable=False)
    temperature = Column(Float, nullable=False)
    humidity = Column(Float, nullable=False)
    pressure = Column(Float, nullable=False)
    status = Column(String, nullable=False)


class SensorData:
    def __init__(self):
        # Room temperature range (adjust if you live in Antarctica)
        self.min_temp = 18.0
        self.max_temp = 26.0
        self.min_humidity = 30.0
        self.max_humidity = 65.0

    def generate_reading(self):
        return {
            "timestamp": datetime.now().isoformat(),
            "temperature": round(random.uniform(self.min_temp, self.max_temp), 1),  # nosec #noqa: S311
            "humidity": round(random.uniform(self.min_humidity, self.max_humidity), 1),  # nosec #noqa: S311
            "pressure": round(random.uniform(1000, 1030), 1),  # nosec #noqa: S311
            "status": random.choice(["normal", "warning", "critical"]),  # nosec #noqa: S311
        }

    def save_reading(self, data: Dict[str, Any]) -> None:
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
            db.add(db_reading)
            db.commit()
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()


# Store the last 20 readings (because nobody cares about data from 1995)
recent_readings: Deque[Dict[str, Any]] = deque(maxlen=20)

# Create tables
Base.metadata.create_all(bind=engine)
