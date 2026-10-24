#!/usr/bin/env python3
"""Read-only check that FastAPI Cloud projects LAN Prometheus Akvorado jobs."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

CLOUD_ORIGIN = "https://fastapi-sample.fastapicloud.dev"
LAN_ORIGIN = "http://172.17.0.24:9090"
JOBS = ("akvorado_inlet", "akvorado_outlet")
QUERY = 'up{job=~"akvorado_inlet|akvorado_outlet"}'
MAX_RESPONSE = 4 * 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    """Do not pass diagnostic authentication to a redirect target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_json(url: str, *, key: str = "") -> dict[str, Any]:
    """Fetch a fixed origin with strict response bounds; never print secrets."""
    headers = {"Accept": "application/json"}
    if key and url.startswith(f"{CLOUD_ORIGIN}/"):
        headers["X-Diagnostics-Key"] = key
    opener = build_opener(ProxyHandler({}), NoRedirect())
    request = Request(url, headers=headers)
    with opener.open(request, timeout=5) as response:
        payload = response.read(MAX_RESPONSE + 1)
    if len(payload) > MAX_RESPONSE:
        raise ValueError("response_limit_exceeded")
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("unexpected_response")
    return data


def observed_up(payload: dict[str, Any]) -> dict[str, float]:
    """Accept only binary target series for the two known Akvorado jobs."""
    data = payload.get("data")
    if payload.get("status") != "success" or not isinstance(data, dict):
        return {}
    result = data.get("result")
    if data.get("resultType") != "vector" or not isinstance(result, list):
        return {}
    observed: dict[str, float] = {}
    for sample in result:
        if not isinstance(sample, dict):
            continue
        labels = sample.get("metric")
        value = sample.get("value")
        if not isinstance(labels, dict) or labels.get("job") not in JOBS:
            continue
        if not isinstance(value, list) or len(value) != 2:
            continue
        if str(value[1]) not in ("0", "1"):
            continue
        job = labels["job"]
        current = float(value[1])
        observed[job] = (
            min(observed[job], current) if job in observed else current
        )
    return observed


def compare(
    lan: dict[str, float], board: dict[str, Any]
) -> tuple[dict[str, str], bool]:
    """Do not mistake a healthy scrape for verified NetFlow delivery."""
    metrics = board.get("platform_metrics")
    if not isinstance(metrics, dict):
        return {job: "cloud_snapshot_missing" for job in JOBS}, False
    projected = metrics.get("exporter_jobs")
    if not isinstance(projected, dict):
        projected = {}
    statuses: dict[str, str] = {}
    for job in JOBS:
        actual, cloud = lan.get(job), projected.get(job)
        if actual is None:
            statuses[job] = "lan_scrape_unverified"
        elif not isinstance(cloud, (float, int)) or cloud not in (0, 1):
            statuses[job] = "cloud_metric_not_observed"
        elif float(cloud) != actual:
            statuses[job] = "lan_cloud_mismatch"
        else:
            statuses[job] = "scrape_projected_up" if actual == 1 else "scrape_projected_down"
    complete = all(statuses[job] == "scrape_projected_up" for job in JOBS)
    return statuses, complete


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.check:
        parser.error("--check required; this script never changes runtime")
    query = urlencode({"query": QUERY})
    urls = (
        (f"{LAN_ORIGIN}/api/v1/query?{query}", ""),
        (f"{CLOUD_ORIGIN}/api/health-board", os.getenv("DIAGNOSTICS_ACCESS_KEY", "")),
    )
    results: list[dict[str, Any]] = []
    for index, (url, key) in enumerate(urls):
        try:
            results.append(fetch_json(url, key=key))
        except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            kind = "LAN" if index == 0 else "CLOUD"
            status = exc.code if isinstance(exc, HTTPError) else "unavailable"
            print(f"{kind}: read failed; HTTP={status} exception={type(exc).__name__}")
            if kind == "CLOUD" and status in (401, 403):
                print(
                    "CLOUD: authorization_denied; Akvorado projection=unverified. "
                    "Review diagnostics key, trusted CIDRs, Cloudflare Access "
                    "and public-read policy. Do not bypass access controls."
                )
                print(
                    "CLOUD: diagnostics_key=" +
                    ("configured" if key else "not_provided")
                )
            return 1
    board = results[1]
    metrics = board.get("platform_metrics")
    configured = metrics.get("configured") if isinstance(metrics, dict) else None
    state = metrics.get("state") if isinstance(metrics, dict) else None
    print(f"FastAPI cloud: prometheus_configured={configured} telemetry_state={state}")
    statuses, complete = compare(observed_up(results[0]), board)
    for job in JOBS:
        print(f"{job}: {statuses[job]}")
    print(
        "NOTE: scrape UP proves Prometheus can collect metrics; it does not "
        "confirm pfSense UDP flows, Kafka messages or ClickHouse writes."
    )
    print("PASS: both target scrapes projected" if complete else "INCOMPLETE: telemetry projection")
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
