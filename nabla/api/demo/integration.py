import requests
import random
import os


from fastapi import APIRouter, HTTPException, status

from ddtrace.trace import tracer
from opentelemetry import trace
from opentelemetry.trace.status import Status, StatusCode

from nabla.utils.logger import logger

from nabla.utils.misc import timed_operation

from nabla.api.v1 import pong

router = APIRouter()


API_GATEWAY_URL = os.environ.get(
    "API_GATEWAY_URL",
    "https://krakend.service.gra.dev.consul",
)


# Base URL of https://httpbin.org/
HTTPBIN_URL = os.environ.get("HTTPBIN_URL", "https://httpbin.org")


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
