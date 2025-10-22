import asyncio
import os
import random
import secrets
from typing import Optional
from uuid import uuid4

import requests
from fastapi import APIRouter, HTTPException, status
from fastapi_cache.decorator import cache
from fastapi_featureflags import FeatureFlags, feature_enabled, feature_flag
from fastapi_mail import FastMail, MessageSchema, MessageType
from fastmcp import FastMCP
from opentelemetry import trace
from opentelemetry.trace.status import Status, StatusCode
from starlette.responses import JSONResponse

from nabla.api.demo.socket.redis import REDIS_CHANNEL, redis
from nabla.auth.controller import AuthController
from nabla.utils.email import EmailSchema, conf
from nabla.utils.logger import logger
from nabla.utils.misc import timed_operation
from nabla.utils.prometheus import API_REQUEST_COUNTER, API_REQUEST_SUMMARY

router = APIRouter()

mcp = FastMCP(name="DemoServer")

# TODO switch to unleash feature flagq
FeatureFlags()
# FeatureFlags.load_conf_from_url("https://pastebin.com/raw/4Ai3j2DC")
FeatureFlags.load_conf_from_dict({"web_only": False, "web_1": True, "web_2": False, "web_3": True, "web_4": False})
FeatureFlags.reload_feature_flags()
print("Enabled Features:", FeatureFlags.get_features())

# The demo sample project to test the tracing
DEMO_SAMPLE_URL = os.environ.get(
    "DEMO_SAMPLE_URL",
    "http://test-haproxy-demo-ateam.service.gra.dev.consul",
)


POOL = list(range(1, 7))
SIZE = 4


def string_secret():
    return random.sample(POOL, SIZE)  # nosec


def uniform_secret():
    return secrets.randbelow(30)
    # return random.uniform(0, 3)  # nosec


@feature_flag("web_1")
@cache()
@router.get("/demo/random")
async def demo_random():
    try:
        # global redis
        # redis = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT)
        secret = uniform_secret()

        # Validate interval (don't let users sleep for too long)
        secret = max(1, min(secret, 10))  # Between 1-10 seconds

        logger.info(f"set random number {secret} to redis")
        await redis.set(REDIS_CHANNEL + ".randomnumber", secret)
        logger.info(f"get random number {secret} from redis")
        result = await redis.get(REDIS_CHANNEL + ".randomnumber")
        if result is None:
            return str(uuid4())  # Fallback to uuid if key doesn't exist
        return str(result)
    except redis.RedisError:
        return str(uuid4())  # Fallback to uuid on connection error


@feature_flag("web_1")
@router.get("/demo/items/{item_id}")
async def read_item(item_id: int, q: Optional[str] = None):
    logger.info(f"Get items : {item_id}")  # [logging-fstring-interpolation]

    # Validate interval (don't let users sleep for too long)
    item_id = max(1, min(item_id, 10))  # Between 1-10 seconds

    API_REQUEST_COUNTER.labels(
        method="GET",
        endpoint="/items/{item_id}",
        http_status=200,
    ).inc()
    API_REQUEST_SUMMARY.labels(method="GET", endpoint="/items/{item_id}").observe(0.1)

    # Example of storing data in Redis
    await redis.set(f"{REDIS_CHANNEL}.item_{item_id}", q or "No Query")

    # yield cached_value

    if item_id % 2 == 0:
        # mock io - wait for x seconds
        # seconds = uniform_secret()
        seconds = item_id
        logger.info(f"Sleeping for {seconds} seconds")
        await asyncio.sleep(seconds)

    cached_value = await redis.get(f"{REDIS_CHANNEL}.item_{item_id}")

    if cached_value is None:
        logger.info(f"Cached value is None for item_id: {item_id}")
        cached_value = "None"

    return {"item_id": item_id, "q": cached_value}


# We are targetting direct demo hotrod service to test tracing
@feature_flag("web_2")
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
            response = requests.request("GET", url, timeout=1, verify=False)

            response.raise_for_status()
            logger.info(f"Dispatch customer response is : {response.json()}")

            return {response.json()["ETA"]}
        except Exception as ex:
            logger.error(f"Error while dispatching customer due to: {ex}")
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
            logger.info("Dispatch customer done")


# DEMO_SAMPLE_URL "http://test-haproxy-demo-ateam.service.gra.dev.consul"
# http://frontnuxt-stats.service.gra.uat.consul/health
# http://frontnuxt-stats.service.gra.uat.consul/?stats;csv
# http://test-haproxy-stats-ateam.service.gra.dev.consul/dev?stats;csv
# http://test-haproxy-webapp-prometheus-ateam.service.gra.dev.consul/metrics


@router.get("/demo/auth")
def root():
    logger.info("Hello")
    """
    Root endpoint that provides a welcome message and documentation link.
    """
    return AuthController.read_root()


# We are targetting dev service
@feature_flag("web_4")
@router.get("/demo/dev/heatlh")
async def demo_dev_health():
    if feature_enabled("web_3"):
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
                logger.info("Test demo service health done")


@feature_flag("web_4")
@router.get("/demo/internal-api/")
def demo_internal_api():
    logger.info("Dispatch customer (for tracing)")

    customer_ids = [123, 392, 731, 567]
    for customer_id in customer_ids:
        dp_customer_id = dispatch_customer(customer_id)
        logger.info(f"Dispatched customer : {dp_customer_id}")

    return status.HTTP_200_OK


@router.post("/demo/email")
async def simple_send(email: EmailSchema) -> JSONResponse:
    html = """<p>Hi this test mail, thanks for using Fastapi-mail</p> """

    message = MessageSchema(
        subject="Fastapi-Mail module",
        recipients=email.dict().get("email"),
        body=html,
        subtype=MessageType.html,
    )

    fm = FastMail(conf)
    await fm.send_message(message)
    return JSONResponse(status_code=200, content={"message": "email has been sent"})
