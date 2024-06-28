import os

import requests
from dd_import.environment import Environment
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning

from nabla.logger import logger


DD_URL = os.environ.get("DD_URL", "http://graansible01:8080")
DD_API_TOKEN = os.environ.get("DD_API_TOKEN", "xxx")
HEADERS = {
    "accept": "application/json",
    "Content-Type": "application/json",
    'Authorization': "Token {}".format(DD_API_TOKEN)
}


def get_products():
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

    except Exception as e:
        logger.error(f"Error while retreibing product due to: {e}")
        exit(1)

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
