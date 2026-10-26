#!/usr/bin/env python3
"""Bounded, no-secret HTTP triage for the /api UI on Cloud or TrueNAS.

Only the pinned origins and fixed GET paths are allowed. No auth headers,
cookies, response bodies, redirect following, or homelab secret material.
"""
from __future__ import annotations

import argparse
import json
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

TARGETS = {
    "cloud": "https://fastapi-sample.fastapicloud.dev",
    "staging": "https://sample.albandrieu.com",
    "truenas": "http://172.17.0.24:8091",
}
PATHS = ("/api", "/api/ui/session", "/api/ui/services")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


def check(target: str) -> dict:
    client = build_opener(ProxyHandler({}), NoRedirect())
    checks = []
    for path in PATHS:
        start = time.monotonic()
        state = "transport_unverified"
        try:
            with client.open(
                Request(TARGETS[target] + path, method="GET", headers={"Accept": "application/json"}),
                timeout=3,
            ) as response:
                state = "http_" + str(response.status)
        except HTTPError as error:
            state = "http_" + str(error.code)
            error.close()
        except URLError as error:
            reason = error.reason
            if isinstance(reason, socket.gaierror):
                state = "dns_failure"
            elif isinstance(reason, ConnectionRefusedError):
                state = "tcp_refused"
            elif isinstance(reason, (socket.timeout, TimeoutError)):
                state = "timeout"
        except (OSError, TimeoutError):
            state = "timeout_or_network_failure"
        checks.append({
            "path": path, "state": state,
            "elapsed_ms": min(round(1000 * (time.monotonic() - start)), 9999),
        })
    return {"component": "api_ui_transport", "target": target, "requests": checks}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=sorted(TARGETS), required=True)
    args = parser.parse_args(argv)
    print(json.dumps(check(args.target), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
