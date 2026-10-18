"""The sensor SSE stream keeps working when the app started without PostgreSQL."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from nabla.api.demo import models, sensor


@pytest.mark.asyncio
async def test_stream_skips_database_persistence_without_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    save_to_db = AsyncMock(side_effect=AssertionError("PostgreSQL must not be used"))
    save_to_redis = AsyncMock()
    monkeypatch.setattr(models.SensorData, "save_reading_to_db", save_to_db)
    monkeypatch.setattr(models.SensorData, "save_reading_to_redis", save_to_redis)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(database_available=False)))

    response = await sensor.stream_sensor_data(request, interval=1)
    first_event = await anext(response.body_iterator)
    await response.body_iterator.aclose()

    assert "sensor_update" in str(first_event)
    save_to_db.assert_not_awaited()
    save_to_redis.assert_awaited_once()
