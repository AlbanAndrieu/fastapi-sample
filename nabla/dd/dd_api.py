import os

import requests

DD_BASE_URL = os.environ.get("DD_BASE_URL", "http://graansible01:8080")
DD_API_TOKEN = os.environ.get("DD_API_TOKEN", "xxx")
HEADERS = {
    "accept": "application/json",
    "Content-Type": "application/json",
    'Authorization': "Token {}".format(DD_API_TOKEN)
}


def get_products():
    response = requests.get(
        f"{DD_BASE_URL}/api/v2/products/", headers=HEADERS, timeout=30
    )
    response.raise_for_status()
    return {product["name"]: product["id"] for product in response.json()["results"]}


def counts_by_product_id(id):
    data = {
        "include_finding_notes": False,
        "include_finding_images": False,
        "include_executive_summary": False,
        "include_table_of_contents": False,
    }

    response = requests.post(
        f"{DD_BASE_URL}/api/v2/products/{id}/generate_report/",
        headers=HEADERS,
        json=data,
        timeout=30,
    )

    counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}

    for finding in response.json()["findings"]:
        if finding["active"]:
            counts[finding["severity"]] += 1

    return counts
