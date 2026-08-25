---
name: redis-async-lifecycle
description: Review or change Redis asyncio clients, FastAPI lifespan cleanup, PubSub listeners, redis-py dependency constraints, lockfiles, or tests without regressing between close() and aclose().
license: Apache-2.0
role: reviewer
---

# Redis asyncio lifecycle

## Goal

Keep Redis resources compatible with the installed redis-py API and owned by the
FastAPI lifespan. Prevent startup and shutdown failures caused by code/lockfile
drift or by mixing synchronous and asynchronous clients.

## Repository contract

This repository uses `redis.asyncio.Redis` and requires redis-py
`>=5.3.1,<6`.

- Close an asynchronous `Redis` client with `await client.aclose()`.
- Close an asynchronous `PubSub` object with `await pubsub.aclose()`.
- Never replace these calls with un-awaited `close()`.
- Do not add a compatibility fallback to `close()`; update the dependency and
  lockfile atomically when the required API changes.
- Distinguish `redis.Redis` from `redis.asyncio.Redis` before reviewing a
  cleanup call.

## Lifecycle ownership

Create client objects without opening network connections during module import.
Connect, start listeners and register cleanup from the application lifespan.
Use `AsyncExitStack` or an equivalent application-owned cleanup path so normal
shutdown, cancellation and partial startup failure release every resource.

Keep background listener tasks named, cancellation-safe and bounded by the
lifespan. A PubSub created by a listener must be closed in `finally`.

## Dependency workflow

Before changing a Redis lifecycle call:

1. Read every Redis constraint in `pyproject.toml`.
2. Inspect the resolved redis-py version in `uv.lock`.
3. Verify the target API against the installed asynchronous class, not memory or
    a synchronous-client example.
4. Update duplicate dependency groups and `uv.lock` in the same commit.
5. Run `uv lock --check` after `uv lock --upgrade-package redis`.

Do not hand-edit only the declared constraint or only the resolved package.
Code, dependency metadata and the lockfile form one compatibility contract.

## Regression tests

Mocks may verify call order, but they must not be the only API-compatibility
test. Keep a test that imports the real installed classes and asserts that
`Redis.aclose` and `PubSub.aclose` are coroutine functions.

Run at minimum:

```bash
uv lock --check
uv run ruff format --check nabla tests
uv run ruff check nabla tests
uv run pytest tests/unit/test_redis_asyncio_contract.py tests/unit/test_lifespan.py
uv run python -c "from redis.asyncio import Redis; assert hasattr(Redis, 'aclose')"
```

Also search changed code for `.close()` and `.aclose()`; classify each
receiver as synchronous or asynchronous before approving it.
