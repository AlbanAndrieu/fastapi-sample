import asyncio
import json
import weakref
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sse_starlette import EventSourceResponse

from nabla.api.demo.models import SensorData, recent_readings

router = APIRouter()

sensor = SensorData()

templates = Jinja2Templates(directory="templates")


active_connections: weakref.WeakSet[Any] = weakref.WeakSet()


@router.get("/stream/{interval}")
async def stream_sensor_data(interval: int = 2):
    # Validate interval (don't let users DoS your server)
    interval = max(1, min(interval, 60))  # Between 1-60 seconds

    if len(active_connections) > 100:  # Adjust based on your server
        raise HTTPException(429, "Too many connections")
    """The magic streaming endpoint that makes everything work"""

    async def event_generator():
        try:
            while True:
                # Generate new sensor reading
                data = sensor.generate_reading()
                recent_readings.append(data)  # Store for charts

                # Save to PostgreSQL
                sensor.save_reading(data)

                # Send to all connected browsers
                yield {"event": "sensor_update", "data": json.dumps(data)}
                await asyncio.sleep(interval)  # Update every X seconds
        except asyncio.CancelledError:
            # User closed browser/tab - no drama, just stop
            pass

    return EventSourceResponse(event_generator())


@router.get("/chart-data")
async def get_chart_data(request: Request):
    """Prepare data for Chart.js visualization"""
    # Ensure we have enough data for charts
    if len(recent_readings) < 20:
        for _ in range(20):
            recent_readings.append(sensor.generate_reading())

    temp_data = [r["temperature"] for r in recent_readings]
    humidity_data = [r["humidity"] for r in recent_readings]
    pressure_data = [r["pressure"] for r in recent_readings]
    labels = [str(i) for i in range(len(recent_readings))]

    return templates.TemplateResponse(
        "chart_data.html",
        {
            "request": request,
            "temp_data": json.dumps(temp_data),
            "humidity_data": json.dumps(humidity_data),
            "pressure_data": json.dumps(pressure_data),
            "labels": json.dumps(labels),
        },
    )
