import asyncio
import json
import os
import time
import weakref
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sse_starlette import EventSourceResponse

from nabla.api.demo.charts import ChartFactory
from nabla.api.demo.models import (
    SensorData,
    SensorEvent,
    detect_anomalies,
    get_sensor_dataframe,
    get_statistical_summary,
    recent_readings,
    serialize_dates,
)
from nabla.api.demo.socket.redis import (
    REDIS_CHANNEL,
    REDIS_SENSOR_CHANNEL,
    REDIS_TASK_QUEUE,
    publish_event,
    redis,
)
from nabla.config_settings import APP_RUNTIME_VERSION
from nabla.rate_limit import limiter
from nabla.utils.logger import logger

router = APIRouter()

templates = Jinja2Templates(directory="templates")
sensor = SensorData()
chart_factory = ChartFactory()

active_connections: weakref.WeakSet[Any] = weakref.WeakSet()


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    """Read a bounded integer interval from the environment."""
    raw_value = os.environ.get(name, str(default))
    try:
        value = int(raw_value)
    except ValueError:
        logger.warning("invalid_refresh_interval", variable=name, value=raw_value, default=default)
        return default
    return max(minimum, min(value, maximum))


DASHBOARD_REFRESH_INTERVAL_SECONDS = _bounded_env_int("DASHBOARD_REFRESH_INTERVAL_SECONDS", 0, 0, 86400)
CHARTS_REFRESH_INTERVAL_SECONDS = _bounded_env_int("CHARTS_REFRESH_INTERVAL_SECONDS", 10, 1, 3600)
SSE_STREAM_INTERVAL_SECONDS = _bounded_env_int("SSE_STREAM_INTERVAL_SECONDS", 5, 1, 60)
SSE_RETRY_INTERVAL_MILLISECONDS = _bounded_env_int("SSE_RETRY_INTERVAL_MILLISECONDS", 5000, 1000, 60000)


# Performance monitoring
class DashboardMetrics:
    def __init__(self):
        self.connection_count = 0
        self.chart_generation_times = []
        self.total_requests = 0

    def track_connection(self):
        self.connection_count += 1
        logger.info(
            f"New SSE connection established. Active connections: {self.connection_count}",
        )

    def track_disconnection(self):
        self.connection_count = max(0, self.connection_count - 1)
        logger.info(
            f"SSE connection closed. Active connections: {self.connection_count}",
        )

    def track_chart_generation(self, duration: float):
        self.chart_generation_times.append(duration)
        if duration > 1.0:  # Slow chart generation
            logger.warning(f"Slow chart generation detected: {duration:.2f}s")
        else:
            logger.debug(f"Chart generated in {duration:.3f}s")

    def track_request(self):
        self.total_requests += 1
        if self.total_requests % 100 == 0:  # Log every 100 requests
            logger.info(f"Total requests served: {self.total_requests}")


metrics = DashboardMetrics()


@router.get("/", response_class=HTMLResponse, operation_id="sensor_dashboard")
@limiter.limit("100/second")
def dashboard(request: Request):
    """Main dashboard with real-time Plotly charts"""
    metrics.track_request()
    logger.info(f"Dashboard accessed from {request.client.host}")
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "dashboard_refresh_interval_seconds": DASHBOARD_REFRESH_INTERVAL_SECONDS,
            "charts_refresh_interval_seconds": CHARTS_REFRESH_INTERVAL_SECONDS,
            "sse_stream_interval_seconds": SSE_STREAM_INTERVAL_SECONDS,
        },
    )


@router.post("/events")
@limiter.limit("100/second")
async def post_sensor_event(event: SensorEvent, request: Request):
    start_time = time.perf_counter()
    await handle_sensor_event(event)
    duration = time.perf_counter() - start_time
    return {"status": "received", "duration_ms": round(duration * 1000, 2)}


@router.get("/stream")
@router.get("/stream/{interval}")
# @limiter.limit("100/second")
async def stream_sensor_data(interval: int = SSE_STREAM_INTERVAL_SECONDS):
    """Stream live sensor data via SSE"""
    metrics.track_connection()
    logger.info("Starting SSE stream for sensor data")

    # Validate interval (don't let users DoS your server)
    interval = max(1, min(interval, 60))  # Between 1-60 seconds

    if len(active_connections) > 100:  # Adjust based on your server
        raise HTTPException(429, "Too many connections")
    """The magic streaming endpoint that makes everything work"""

    async def event_generator():
        # generate_sensor_data(interval)
        try:
            while True:
                # Generate new sensor reading
                data = sensor.generate_reading()
                recent_readings.append(data)  # Store for charts

                logger.debug(
                    f"Generated sensor reading: temp={data['temperature']}°C, status={data['status']}",
                )

                # Save to PostgreSQL and Redis
                await sensor.save_reading(data)

                # Send to all connected browsers
                yield {
                    "event": "sensor_update",
                    "retry": SSE_RETRY_INTERVAL_MILLISECONDS,
                    "data": json.dumps(
                        data,
                        default=serialize_dates,
                        sort_keys=True,
                        indent=4,
                    ),
                }
                await asyncio.sleep(interval)  # Update every X seconds
        except asyncio.CancelledError:
            logger.info("SSE connection cancelled by client")
            metrics.track_disconnection()
            # User closed browser/tab - no drama, just stop
        except Exception as e:
            logger.error(f"Error in SSE stream: {e}")
            metrics.track_disconnection()
            raise

    return EventSourceResponse(event_generator())


@router.get("/chart-data")
@limiter.limit("100/second")
async def get_chart_data(request: Request):
    """Get chart data for the dashboard"""

    start_time = time.time()
    logger.debug("Starting old chart generation")

    try:
        temp_data = [r["temperature"] for r in recent_readings]
        humidity_data = [r["humidity"] for r in recent_readings]
        pressure_data = [r["pressure"] for r in recent_readings]
        labels = [str(i) for i in range(len(recent_readings))]

        return templates.TemplateResponse(
            request,
            "chart_data.html",
            {
                "temp_data": json.dumps(temp_data),
                "humidity_data": json.dumps(humidity_data),
                "pressure_data": json.dumps(pressure_data),
                "labels": json.dumps(labels),
            },
        )

    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Chart generation failed after {duration:.3f}s: {e}")
        raise


@router.get("/charts")
@limiter.limit("100/second")
async def get_charts(request: Request):
    """Prepare data for Chart.js visualization"""
    """Generate all Plotly charts as HTML"""
    start_time = time.time()
    metrics.track_request()

    try:
        df = get_sensor_dataframe()
        anomalies = detect_anomalies()

        logger.debug(f"Processing {len(df)} sensor readings for chart generation")

        charts_html = {
            "timeseries": chart_factory.create_time_series_chart(df),
            "status": chart_factory.create_status_distribution(df),
            "correlation": chart_factory.create_correlation_heatmap(df),
            "anomalies": chart_factory.create_anomaly_highlights(df, anomalies),
        }

        stats = get_statistical_summary()

        duration = time.time() - start_time
        metrics.track_chart_generation(duration)

        logger.debug("charts_generated", duration_seconds=duration)

        return templates.TemplateResponse(
            request,
            "charts.html",
            {
                "charts": charts_html,
                "stats": stats,
                "anomaly_count": len(anomalies),
            },
        )

    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Chart generation failed after {duration:.3f}s: {e}")
        raise


@router.get("/sensor-data")
@limiter.limit("100/second")
async def get_sensor_data(request: Request):
    """Get current sensor reading for display"""
    metrics.track_request()

    if recent_readings:
        latest = recent_readings[-1]
        logger.debug(f"Serving latest sensor data: {latest['status']} status")
        return templates.TemplateResponse(
            request,
            "sensor_data.html",
            {"sensor_data": latest},
        )

    logger.warning("No sensor data available")
    return templates.TemplateResponse(
        request,
        "sensor_data.html",
        {"sensor_data": None},
    )


@router.get("/health")
async def health_check():
    """Return lightweight runtime health without probing external dependencies."""
    metrics.track_request()

    health_data = {
        "status": "healthy",
        "version": APP_RUNTIME_VERSION,
        "readings_count": len(recent_readings),
        "active_connections": metrics.connection_count,
        "total_requests": metrics.total_requests,
        "timestamp": datetime.now().isoformat(),
        "components": {
            "api": {"status": "healthy"},
            "sensor": {
                "status": "healthy",
                "readings_count": len(recent_readings),
            },
            "streaming": {
                "status": "healthy",
                "active_connections": metrics.connection_count,
            },
            "health_api": {
                "status": "healthy",
                "liveness": "/livez",
                "readiness": "/readyz",
                "deep_health": "/healthz",
                "homelab_health": "/api/homelab/health",
            },
        },
    }

    if metrics.chart_generation_times:
        recent_times = metrics.chart_generation_times[-10:]
        health_data["avg_chart_generation_time"] = sum(recent_times) / len(recent_times)
        health_data["max_chart_generation_time"] = max(recent_times)

    logger.debug(f"Health check: {health_data}")
    return health_data


# Metrics endpoint overridding the default one on main.py
@router.get("/stats")
async def get_metrics():
    """Detailed metrics endpoint for monitoring"""
    metrics.track_request()

    detailed_metrics = {
        "connections": {
            "active": metrics.connection_count,
            "total_requests": metrics.total_requests,
        },
        "data": {
            "readings_stored": len(recent_readings),
            "latest_reading_time": recent_readings[-1]["timestamp"] if recent_readings else None,
        },
        "performance": {
            "chart_generations": len(metrics.chart_generation_times),
            "avg_chart_time": sum(metrics.chart_generation_times) / len(metrics.chart_generation_times) if metrics.chart_generation_times else 0,
            "slow_chart_count": len(
                [t for t in metrics.chart_generation_times if t > 1.0],
            ),
        },
        "timestamp": datetime.now().isoformat(),
    }

    logger.info("Detailed metrics requested")
    return detailed_metrics


@router.get("/queue-status")
async def queue_status():
    length = await redis.llen(REDIS_CHANNEL + REDIS_TASK_QUEUE + REDIS_SENSOR_CHANNEL)
    return {"queue_length": length}


async def handle_sensor_event(event):
    await publish_event(event)
