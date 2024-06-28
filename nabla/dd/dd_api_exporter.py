import os
import random

import requests
from dd_import.environment import Environment
from fastapi import HTTPException, status
from opentelemetry import trace
from opentelemetry.trace.status import Status, StatusCode
from utils.misc import timed_operation

from nabla.logger import logger

random.seed(54321)  # nosec

DD_URL = os.environ.get("DD_URL", "http://graansible01:8080")
DD_API_KEY = os.environ.get("DD_API_KEY", "xxx")

HEADERS = {
    "accept": "application/json",
    "Content-Type": "application/json",
    'Authorization': "Token {}".format(DD_API_KEY)
}


def get_products():
    with timed_operation('Product retrieval'):
        try:
            environment = Environment()
            environment.check_environment_languages()
            logger.info(
                f"Get DD environment {environment.url}"
            )
            response = requests.get(
                f"{DD_URL}/api/v2/products/", headers=HEADERS, timeout=30
            )
            response.raise_for_status()
            return {product["name"]: product["id"] for product in response.json()["results"]}

        except Exception as ex:
            logger.error(f"Error while retreiving product due to: {ex}")
            span = trace.get_current_span()

            # generate random number
            seconds = random.uniform(0, 30)  # nosec

            # record_exception converts the exception into a span event.
            exception = IOError("Failed at " + str(seconds))
            span.record_exception(exception)
            span.set_attributes({'est': True})
            # Update the span status to failed.
            span.set_status(Status(StatusCode.ERROR, "internal error"))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Got sadness")
            exit(1)
        finally:
            logger.info('Product retrieval done')


def counts_by_product_id(id):
    data = {
        "include_finding_notes": False,
        "include_finding_images": False,
        "include_executive_summary": False,
        "include_table_of_contents": False,
    }

    response = requests.post(
        f"{DD_URL}/api/v2/products/{id}/generate_report/",
        headers=HEADERS,
        json=data,
        timeout=30,
    )

    counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}

    for finding in response.json()["findings"]:
        if finding["active"]:
            counts[finding["severity"]] += 1

    return counts
