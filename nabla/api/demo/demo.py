import asyncio
import os
import random
from typing import Optional

import requests
from fastapi import APIRouter, HTTPException, status
from opentelemetry import trace
from opentelemetry.trace.status import Status, StatusCode

from nabla.utils.logger import logger
from nabla.utils.misc import timed_operation
from nabla.utils.prometheus import API_REQUEST_COUNTER, API_REQUEST_SUMMARY

router = APIRouter()


# The demo sample project to test the tracing
DEMO_SAMPLE_URL = os.environ.get(
    "DEMO_SAMPLE_URL",
    "http://test-haproxy-demo-ateam.service.gra.dev.consul",
)


@router.get("/demo/items/{item_id}")
async def read_item(item_id: int, q: Optional[str] = None):
    logger.info(f"Get items : {item_id}")  # [logging-fstring-interpolation]

    API_REQUEST_COUNTER.labels(
        method="GET",
        endpoint="/items/{item_id}",
        http_status=200,
    ).inc()
    API_REQUEST_SUMMARY.labels(method="GET", endpoint="/items/{item_id}").observe(0.1)
    if item_id % 2 == 0:
        # mock io - wait for x seconds
        seconds = random.uniform(0, 3)  # nosec # noqa: S311
        await asyncio.sleep(seconds)
    return {"item_id": item_id, "q": q}


# We are targetting direct demo hotrod service to test tracing
@router.get("/demo/dispatch/customer/{customer_id}")
async def dispatch_customer(customer_id: int, q: Optional[str] = None):
    with timed_operation("demo_dispatch_customer"):
        try:
            logger.info(
                f"Dispatch customer : {customer_id}",
            )  # [logging-fstring-interpolation]

            # API_REQUEST_COUNTER.labels(
            #     method="GET",
            #     endpoint="/dispatch/customer/{customer_id}",
            #     http_status=200,
            # ).inc()
            # API_REQUEST_SUMMARY.labels(
            #     method="GET", endpoint="/dispatch/customer/{customer_id}"
            # ).observe(0.1)

            url = f"{DEMO_SAMPLE_URL}/dispatch?customer={customer_id}"
            response = requests.request("GET", url, timeout=1)

            response.raise_for_status()
            logger.info(f"Dispatch customer response is : {response.json()}")

            return {response.json()["ETA"]}
        except Exception as ex:
            logger.error(f"Error while dispatching customer due to: {ex}")
            span = trace.get_current_span()

            # generate random number
            seconds = random.uniform(0, 30)  # nosec  # noqa: S311

            # record_exception converts the exception into a span event.
            exception = IOError("Failed at " + str(seconds))
            span.record_exception(exception)
            span.set_attributes({"est": True})
            # Update the span status to failed.
            span.set_status(Status(StatusCode.ERROR, "internal error"))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Got sadness",
            ) from ex
        finally:
            logger.info("Dispatch customer done")


# DEMO_SAMPLE_URL "http://test-haproxy-demo-ateam.service.gra.dev.consul"
# http://frontnuxt-stats.service.gra.uat.consul/health
# http://frontnuxt-stats.service.gra.uat.consul/?stats;csv
# http://test-haproxy-stats-ateam.service.gra.dev.consul/dev?stats;csv
# http://test-haproxy-webapp-prometheus-ateam.service.gra.dev.consul/metrics


# We are targetting dev service
@router.get("/demo/dev/heatlh")
async def demo_dev_health():
    with timed_operation("demo_dev_health"):
        try:
            logger.info("Test demo service health")  # [logging-fstring-interpolation]

            response = requests.request(
                "GET",
                "http://frontnuxt-stats.service.gra.dev.consul/health",
                timeout=1,
            )

            response.raise_for_status()
            logger.info("Demo response is : %s", response.json())

            return {response.json()}
        except Exception as ex:
            logger.error(f"Error while dispatching customer due to: {ex}")
            span = trace.get_current_span()

            # generate random number
            seconds = random.uniform(0, 30)  # nosec  # noqa: S311

            # record_exception converts the exception into a span event.
            exception = IOError("Failed at " + str(seconds))
            span.record_exception(exception)
            span.set_attributes({"est": True})
            # Update the span status to failed.
            span.set_status(Status(StatusCode.ERROR, "internal error"))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Got sadness",
            ) from ex
        finally:
            logger.info("Test demo service health done")


@router.get("/demo/internal-api/")
def demo_internal_api():
    logger.info("Dispatch customer (for tracing)")

    customer_ids = [123, 392, 731, 567]
    for customer_id in customer_ids:
        dp_customer_id = dispatch_customer(customer_id)
        logger.info(f"Dispatched customer : {dp_customer_id}")

    return status.HTTP_200_OK
