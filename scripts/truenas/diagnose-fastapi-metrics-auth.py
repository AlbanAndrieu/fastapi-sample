#!/usr/bin/env python3
"""Read-only, no-secret FastAPI /metrics authentication diagnostic.

This checks the local TrueNAS FastAPI origin, never a public or arbitrary URL.
Neither tokens, response bodies, URLs nor headers are printed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from stat import S_ISREG, S_IROTH, S_IWGRP, S_IWOTH
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

METRICS_URL = "http://127.0.0.1:8091/metrics"
MAX_TOKEN_BYTES = 512
# SSH is pinned to the approved TrueNAS LAN address. Never accept arbitrary
# hosts or shell fragments from CLI arguments.
TRUENAS_SSH_TARGET = re.compile(r"^[a-z_][a-z0-9_-]{0,31}@172[.]17[.]0[.]24$")
_REMOTE_STATES = frozenset({
    "unexpected_anonymous_metrics_access",
    "metrics_key_unconfigured_or_gate_unavailable",
    "key_configured_scraper_credentials_unverified",
    "scrape_auth_accepted",
    "scrape_credential_rejected",
    "authenticated_gate_unavailable",
    "authenticated_probe_unverified",
    "metrics_origin_unverified",
    "token_file_invalid_or_unreadable",
})


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
        if metadata.st_mode & (S_IROTH | S_IWGRP | S_IWOTH):
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



def ssh_status(target: str, token_file: Path | None = None, port: int = 22) -> tuple[dict, int]:
    """Execute the same read-only probe on TrueNAS over authenticated SSH.

    No secrets are sent by this process. A token file, when specified, is
    opened only on TrueNAS by the remote Python process. Never echo SSH
    stderr, remote output beyond allowlisted fields, or the SSH target.
    """
    if not TRUENAS_SSH_TARGET.fullmatch(target) or not 1 <= port <= 65535:
        return {"state": "ssh_target_invalid", "scrape_authorized": False}, 2
    if token_file is not None and (
        not token_file.is_absolute() or "\x00" in str(token_file)
        or len(str(token_file)) > 256
    ):
        return {"state": "remote_token_path_invalid", "scrape_authorized": False}, 2

    remote_command = "python3 - --check"
    if token_file is not None:
        remote_command += " --token-file " + shlex.quote(str(token_file))
    command = [
        "ssh", "-T", "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "ConnectTimeout=7",
        "-o", "ServerAliveInterval=5",
        "-o", "ServerAliveCountMax=1",
        "-p", str(port), "--", target, remote_command,
    ]
    try:
        source = Path(__file__).read_text(encoding="utf-8")
        completed = subprocess.run(
            command, input=source, capture_output=True, text=True,
            timeout=20, check=False,
        )
        if completed.returncode not in (0, 1, 2) or len(completed.stdout) > 4096:
            raise ValueError("ssh_runtime_unverified")
        payload = json.loads(completed.stdout)
        if (
            completed.returncode == 2
            and isinstance(payload, dict)
            and set(payload) == {"state", "scrape_authorized"}
            and payload["state"] == "token_file_invalid_or_unreadable"
            and payload["scrape_authorized"] is False
        ):
            return {"origin": "truenas_ssh",
                    "state": "remote_token_file_invalid_or_unreadable",
                    "scrape_authorized": False}, 2
        if (
            not isinstance(payload, dict)
            or payload.get("state") not in _REMOTE_STATES
            or payload.get("origin") != "truenas_loopback"
            or payload.get("path") != "/metrics"
            or type(payload.get("credentials_tested")) is not bool
            or type(payload.get("scrape_authorized")) is not bool
            or any(
                payload.get(key) is not None
                and (type(payload[key]) is not int or not 100 <= payload[key] <= 599)
                for key in ("anonymous_http", "authenticated_http")
            )
        ):
            raise ValueError("invalid_remote_report")
        approved = (
            completed.returncode == 0
            and payload["scrape_authorized"]
            and payload["state"] == "scrape_auth_accepted"
            and payload["credentials_tested"]
            and payload.get("anonymous_http") == 401
            and payload.get("authenticated_http") == 200
        )
        # Never forward arbitrary remote JSON properties or messages.
        report = {
            "origin": "truenas_ssh",
            "path": "/metrics",
            "anonymous_http": payload.get("anonymous_http"),
            "authenticated_http": payload.get("authenticated_http"),
            "credentials_tested": payload["credentials_tested"],
            "scrape_authorized": approved,
            "state": payload["state"],
        }
        return report, 0 if approved else (
            1 if completed.returncode == 1 else 2
        )
    except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired):
        return {"state": "ssh_unavailable_or_report_invalid",
                "scrape_authorized": False}, 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--token-file", type=Path, help="Private scrape token file on the executing host (never logged)")
    parser.add_argument(
        "--ssh-target", help="Run remotely as user@172.17.0.24 over verified SSH",
    )
    parser.add_argument("--ssh-port", type=int, default=22)
    args = parser.parse_args()
    if not args.check:
        parser.error("only --check is supported")
    if args.ssh_target:
        # --token-file denotes a path on TrueNAS in this mode. Do not
        # forward METRICS_SCRAPE_KEY from the workstation over SSH.
        result, exit_code = ssh_status(args.ssh_target, args.token_file, args.ssh_port)
        print(json.dumps(result, sort_keys=True))
        return exit_code
    if args.ssh_port != 22:
        parser.error("--ssh-port requires --ssh-target")
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
