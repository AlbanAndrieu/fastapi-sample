"""Regression contract for the redis-py asynchronous lifecycle API."""

import inspect

from redis.asyncio import Redis
from redis.asyncio.client import PubSub


def test_redis_async_clients_expose_awaitable_aclose() -> None:
    """The lifespan and listener cleanup require redis-py 5's async API."""
    assert inspect.iscoroutinefunction(Redis.aclose)
    assert inspect.iscoroutinefunction(PubSub.aclose)
