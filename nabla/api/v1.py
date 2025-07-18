import asyncio
import os
import random
from typing import Optional

import redis
import requests
from ddtrace.trace import tracer
from fastapi import APIRouter, HTTPException, status
from opentelemetry import trace
from opentelemetry.trace.status import Status, StatusCode
from starlette.responses import JSONResponse

from nabla.dd.dd_api_exporter import get_products
from nabla.metrics.prometheus import (
    API_REQUEST_COUNTER,
    API_REQUEST_SUMMARY,
    ERROR_COUNT,
)
from nabla.utils.logger import logger
from nabla.utils.misc import timed_operation

# logger = logging.getLogger(__name__)
# logger.setLevel(logging.INFO)

# The demo sample project to test the tracing
DEMO_SAMPLE_URL = os.environ.get(
    "DEMO_SAMPLE_URL",
    "http://test-haproxy-demo-ateam.service.gra.dev.consul",
)

# Base URL of https://httpbin.org/
HTTPBIN_URL = os.environ.get("HTTPBIN_URL", "https://httpbin.org")

API_GATEWAY_URL = os.environ.get(
    "API_GATEWAY_URL",
    "https://krakend.service.gra.dev.consul",
)

QUOTES = [
    "Strive not to be a success, but rather to be of value. - Albert Einstein",
    "Believe you can and you're halfway there. - Theodore Roosevelt",
    "The future belongs to those who believe in the beauty of their dreams. - Eleanor Roosevelt",
]

router = APIRouter(prefix="/v1")


@router.get("/items/{item_id}")
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


# We are targetting demo hotrod service
@router.get("/demo/heatlh")
async def demo_health():
    with timed_operation("demo_health"):
        try:
            logger.info("Test demo service health")  # [logging-fstring-interpolation]

            response = requests.request(
                "GET",
                "http://frontnuxt-stats.service.gra.uat.consul/health",
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


@router.get("/message")
async def demo_message():
    return {"Hello": "World"}


@router.get("/random")
async def demo_random():
    try:
        redis_client = redis.StrictRedis(host="127.0.0.1", port=6379)
        result = redis_client.get("randomnumber")
        if result is None:
            return str(uuid4())  # Fallback to uuid if key doesn't exist
        return str(result)
    except redis.RedisError:
        return str(uuid4())  # Fallback to uuid on connection error


@router.get("/invalid")
async def invalid():
    raise ValueError("Invalid ")


@router.get("/exception")
async def exception():
    try:
        raise ValueError("sadness")
    except Exception as ex:
        logger.error(ex, exc_info=True)
        ERROR_COUNT.labels(ex).inc()
        span = trace.get_current_span()

        # generate random number
        seconds = random.uniform(0, 30)  # nosec  # noqa: S311

        # record_exception converts the exception into a span event.
        ioexception = IOError("Failed at " + str(seconds))
        span.record_exception(ioexception)
        span.set_attributes({"est": True})
        # Update the span status to failed.
        span.set_status(Status(StatusCode.ERROR, "internal error"))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Got sadness",
        ) from ex


@router.get("/external-api")
def external_api():
    try:
        seconds = random.uniform(0, 3)  # nosec  # noqa: S311

        logger.info(
            f"Get external api {HTTPBIN_URL} : {seconds}",
        )  # [logging-fstring-interpolation]

        # url = "https://httpbin.org/delay/1"
        url = f"{HTTPBIN_URL}/delay/{seconds}"

        response = requests.request("PUT", url, timeout=5)

        print(response.text)

        # response = requests.put(f"https://httpbin.org/delay/{seconds}", timeout=5)
        response.close()

        return response.text
        # return "ok"
    except Exception as ex:
        logger.error(ex, exc_info=True)
    finally:
        logger.info("DONE")


@router.get("/internal-api/demo")
def demo_internal_api():
    logger.info("Dispatch customer (for tracing)")

    customer_ids = [123, 392, 731, 567]
    for customer_id in customer_ids:
        dp_customer_id = dispatch_customer(customer_id)
        logger.info(f"Dispatched customer : {dp_customer_id}")

    return status.HTTP_200_OK


@router.get("/internal-api/dd")
def dd_internal_api():
    logger.info("Get dd products")

    return get_products()


# We are targeting krakend services
@router.get("/gateway/assistant")
async def gateway_assistant():
    with timed_operation("gateway_assistant"):
        try:
            logger.info(
                "Test gateway service assistant",
            )  # [logging-fstring-interpolation]

            with tracer.trace(
                name="assistant_helper",
                service="assistant_helper",
                resource="another_process",
            ) as span:
                print(pong())

            url = f"{API_GATEWAY_URL}/threads"
            response = requests.request("GET", url, verify=False, timeout=1)

            response.raise_for_status()
            logger.info(f"Gateway assistant response is : {response.json()}")

            return {response.json()}
        except Exception as ex:
            logger.error(f"Error while reaching threads due to: {ex}")
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
            logger.info("Test gateway service assistant done")


@router.get("/ping")
async def ping():
    with tracer.trace("get_quote") as span:
        quote = random.choice(QUOTES) + "\n"  # noqa: S311
        span.set_tag("quote", quote)
        return quote


@router.get("/pong")
async def pong():
    """
    Healthcheck endpoint.
    """
    return JSONResponse({"ping": "pong v1!"})
