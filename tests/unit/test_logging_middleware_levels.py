"""Request log levels: a workstation 503 (optional dependency down) is a warning."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from nabla import middleware


async def _log(monkeypatch: pytest.MonkeyPatch, *, status_code: int, mode: str) -> Mock:
    logger = Mock()
    monkeypatch.setattr(middleware, "logger", logger)
    monkeypatch.setattr(middleware, "runtime_mode", lambda: mode)
    request = SimpleNamespace(method="GET", url=SimpleNamespace(path="/notes/"))

    async def call_next(_request):
        return SimpleNamespace(status_code=status_code)

    await middleware.logging_middleware(request, call_next)
    return logger


@pytest.mark.asyncio
async def test_local_service_unavailable_is_a_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    logger = await _log(monkeypatch, status_code=503, mode="local")

    logger.error.assert_not_called()
    logger.warning.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["fastapi_cloud", "homelab"])
async def test_deployed_service_unavailable_stays_an_error(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    logger = await _log(monkeypatch, status_code=503, mode=mode)

    logger.error.assert_called_once()


@pytest.mark.asyncio
async def test_local_internal_error_stays_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    logger = await _log(monkeypatch, status_code=500, mode="local")

    logger.error.assert_called_once()
