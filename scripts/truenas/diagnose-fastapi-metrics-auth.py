#!/usr/bin/env python3
"""Read-only, no-secret FastAPI /metrics authentication diagnostic.

This checks the local TrueNAS FastAPI origin, never a public or arbitrary URL.
Neither tokens, response bodies, URLs nor headers are printed.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from stat import S_ISREG, S_IROTH
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

METRICS_URL = "http://127.0.0.1:8091/metrics"
MAX_TOKEN_BYTES = 512


class NoRedirect(HTTPRedirectHandler):
    """Reject redirects, including redirects off the loopback origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_token_file(path: Path) -> str | None:
    """Read a private operator-selected token file, never print its contents."""
    if path.is_symlink() or not path.is_file():
        return None
    try:
        metadata = path.stat()
        if not S_ISREG(metadata.st_mode) or metadata.st_size > MAX_TOKEN_BYTES:
            return None
        if metadata.st_mode & S_IROTH:
            return None
        value = path.read_text(encoding="utf-8").strip()
        if not value or not value.isascii() or len(value) > MAX_TOKEN_BYTES or any(char.isspace() for char in value):
            return None
        return value
    except (OSError, UnicodeError, ValueError):
        return None


def http_status(token: str | None, timeout: float = 5.0) -> int | None:
    """Return HTTP status only; disallow proxies, redirects and body logging."""
    opener = build_opener(ProxyHandler({}), NoRedirect())
    headers = {"Accept": "text/plain"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    try:
        with opener.open(Request(METRICS_URL, headers=headers, method="GET"), timeout=timeout) as response:
            return response.status
    except HTTPError as exc:
        exc.close()
        return exc.code
    except (OSError, URLError, ValueError, TimeoutError):
        return None


def assess(anonymous: int | None, authorized: int | None, token_supplied: bool) -> dict:
    """Classify evidence, never infer application readiness from /metrics."""
    if anonymous == 200:
        state = "unexpected_anonymous_metrics_access"
    elif anonymous == 503:
        state = "metrics_key_unconfigured_or_gate_unavailable"
    elif anonymous == 401:
        if not token_supplied:
            state = "key_configured_scraper_credentials_unverified"
        elif authorized == 200:
            state = "scrape_auth_accepted"
        elif authorized == 401:
            state = "scrape_credential_rejected"
        elif authorized == 503:
            state = "authenticated_gate_unavailable"
        else:
            state = "authenticated_probe_unverified"
    else:
        state = "metrics_origin_unverified"
    return {
        "origin": "truenas_loopback",
        "path": "/metrics",
        "anonymous_http": anonymous,
        "authenticated_http": authorized if token_supplied else None,
        "credentials_tested": token_supplied,
        "state": state,
        "scrape_authorized": anonymous == 401 and token_supplied and authorized == 200,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--token-file", type=Path, help="Private read-only scrape token file (never logged)")
    args = parser.parse_args()
    if not args.check:
        parser.error("only --check is supported")
    token = None
    if args.token_file:
        token = read_token_file(args.token_file)
        if token is None:
            print(json.dumps({"state": "token_file_invalid_or_unreadable", "scrape_authorized": False}))
            return 2
    else:
        # An exported secret is optional. Never print or compare a secret to a value in git.
        candidate = os.getenv("METRICS_SCRAPE_KEY", "")
        if candidate and candidate.isascii() and len(candidate) <= MAX_TOKEN_BYTES and not any(c.isspace() for c in candidate):
            token = candidate

    anonymous = http_status(None)
    authorized = http_status(token) if token else None
    outcome = assess(anonymous, authorized, token is not None)
    print(json.dumps(outcome, sort_keys=True))
    if outcome["scrape_authorized"]:
        return 0
    return 1 if outcome["state"] in {
        "unexpected_anonymous_metrics_access", "scrape_credential_rejected"
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
