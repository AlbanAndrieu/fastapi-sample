import os
import random

import aiohttp
import pybreaker
import requests
from ddtrace.trace import tracer
from fastapi import APIRouter, HTTPException, status
from opentelemetry import trace
from opentelemetry.trace.status import Status, StatusCode

from nabla.api.demo.demo import uniform_secret
from nabla.api.v1 import pong
from nabla.utils.logger import logger
from nabla.utils.misc import timed_operation

router = APIRouter()

circuit_breaker_default = pybreaker.CircuitBreaker(fail_max=2, reset_timeout=10)

API_GATEWAY_URL = os.environ.get(
    "API_GATEWAY_URL",
    "https://api.service.gra.uat.consul",
)


# Base URL of https://httpbin.org/
HTTP_BIN_URL = os.environ.get("HTTPBIN_URL", "https://httpbin.org")

# curl "http://metadata.google.internal/computeMetadata/v1/instance/?" -H "Metadata-Flavor: Google"
HTTP_CLOUD_API_URL = os.environ.get(
    "HTTP_CLOUD_API_URL",
    "http://169.254.169.254o/penstack/latest/meta_data.json",
)


@router.get("/async-data")
@circuit_breaker_default
async def get_async_data():
    async with aiohttp.ClientSession() as session:
        async with session.get("{HTTP_BIN_URL}/delay/1") as resp:
            return await resp.json()  # Asynchronous suspension without blocking the event loop


@router.get("/external-api")
@circuit_breaker_default
async def get_external_api():
    try:
        seconds = random.uniform(0, 3)  # nosec  # noqa: S311

        logger.info(
            f"Get external api {HTTP_BIN_URL} : {seconds}",
        )  # [logging-fstring-interpolation]

        # url = "https://httpbin.org/delay/1"
        url = f"{HTTP_BIN_URL}/delay/{seconds}"

        response = requests.request("PUT", url, timeout=5, verify=False)

        print(response.text)

        # response = requests.put(f"https://httpbin.org/delay/{seconds}", timeout=5)
        response.close()

        return response.text
        # return "ok"
    except Exception as ex:
        logger.error(ex, exc_info=True)
    finally:
        logger.info("DONE")


# See https://tonylixu.medium.com/linux-networking-what-is-ip-address-169-254-169-254-f9e23b7332fe
@router.get("/internal-cloud-api")
@circuit_breaker_default
async def get_internal_cloud_api():
    try:
        logger.info(
            f"Get internal cloud api {HTTP_BIN_URL}",
        )  # [logging-fstring-interpolation]

        url = f"{HTTP_BIN_URL}"

        response = requests.request("GET", url, timeout=5)

        print(response.text)

        response.close()

        return response.text
        # return "ok"
    except Exception as ex:
        logger.error(ex, exc_info=True)
    finally:
        logger.info("DONE")


# We are targeting krakend services
@router.get("/gateway/assistant")
@circuit_breaker_default
async def get_gateway_assistant():
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
            seconds = uniform_secret()

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
