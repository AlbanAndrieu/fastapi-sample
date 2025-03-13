import time

import pyroscope
from ddtrace.trace import tracer
from fastapi import APIRouter

from nabla.utils.logger import logger

router = APIRouter()


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
