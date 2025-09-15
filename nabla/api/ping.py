import cProfile
import os
import time

import httpx
import pyroscope
from ddtrace.trace import tracer
from fastapi import APIRouter, Response
from opentelemetry.propagate import inject
from slowapi import Limiter
from slowapi.util import get_remote_address

from nabla.utils.logger import logger

EXPOSE_HOST = os.environ.get("EXPOSE_HOST", "localhost")
EXPOSE_PORT = int(os.environ.get("EXPOSE_PORT", "8080"))
EXPOSE_ENV = os.environ.get("EXPOSE_ENV", "DEV")

TARGET_ONE_HOST = os.environ.get(
    "TARGET_ONE_HOST",
    EXPOSE_HOST,
    # "fastapi-sample.service.gra" + EXPOSE_ENV + "consul",
)
TARGET_TWO_HOST = os.environ.get(
    "TARGET_TWO_HOST",
    EXPOSE_HOST,
    # "fastapi-sample.service.gra" + EXPOSE_ENV + "consul",
)

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

@router.get("/ping")
async def ping():
    # some async operation could happen here
    # example: `notes = await get_all_notes()`
    return {"ping": "pong!"}


@router.get("/io_task")
@tracer.wrap(service="ping_io_task_helper")
async def io_task():
    time.sleep(1)
    logger.error("io task")
    return "IO bound task finish!"


def work(n):
    for i in range(n):
        i * i * i  # pyright: ignore # [pointless-statement]


@router.get("/cpu_task")
async def cpu_task():
    with pyroscope.tag_wrapper({"function": "fast"}):
        work(1000)
    logger.error("cpu task")

    return "CPU bound task finish!"



@router.get("/profile-me")
async def profile_me():
    pr = cProfile.Profile()
    pr.enable()
    result = await chain()  # Business logic to be analyzed
    pr.disable()
    pr.print_stats(sort="cumulative")  # Sort by cumulative time to identify bottlenecks
    return result

@router.get("/error_test")
async def error_test(response: Response):
    logger.error("got error!!!!")
    raise ValueError("value error")

@router.get("/chain")
# @limiter.limit("100/second")
async def chain():
    headers = {}
    inject(headers)  # inject trace info to header
    logger.critical(headers)

    async with httpx.AsyncClient(
        timeout=5.0,
        limits=httpx.Limits(max_connections=100),
    ) as client:
        await client.get(
            f"http://localhost:{EXPOSE_PORT}/",
            headers=headers,
        )
    async with httpx.AsyncClient(
        timeout=5.0,
        limits=httpx.Limits(max_connections=100),
    ) as client:
        await client.get(
            f"http://{TARGET_ONE_HOST}:{EXPOSE_PORT}/io_task",
            headers=headers,
        )
    async with httpx.AsyncClient(
        timeout=5.0,
        limits=httpx.Limits(max_connections=100),
    ) as client:
        await client.get(
            f"http://{TARGET_TWO_HOST}:{EXPOSE_PORT}/cpu_task",
            headers=headers,
        )
    logger.info("Chain Finished")
    return {"path": "/chain"}
