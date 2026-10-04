"""Read-only pfSense split-identity smoke test for the deployed runtime."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import sys
from typing import Literal

import httpx
from pydantic import ValidationError

from nabla.settings.homelab import (
    PfSensePostureProviderSettings,
    PfSenseSecurityProviderSettings,
)


@dataclass(frozen=True, slots=True)
class ProbeExpectation:
    identity: Literal["posture", "security"]
    endpoint: str
    expected_status: int


EXPECTATIONS = (
    ProbeExpectation("posture", "/api/v2/system/version", 200),
    ProbeExpectation("posture", "/api/v2/status/services", 200),
    ProbeExpectation("posture", "/api/v2/services/dns_resolver/settings", 200),
    ProbeExpectation("posture", "/api/v2/system/dns", 200),
    ProbeExpectation("posture", "/api/v2/diagnostics/table?id=snort2c", 403),
    ProbeExpectation("security", "/api/v2/diagnostics/table?id=snort2c", 200),
    ProbeExpectation("security", "/api/v2/status/services", 403),
)


@dataclass(frozen=True, slots=True)
class IdentitySettings:
    base_url: str
    api_key: str
    verify_ssl: bool


def _settings(identity: Literal["posture", "security"]) -> IdentitySettings:
    provider = (
        PfSensePostureProviderSettings()
        if identity == "posture"
        else PfSenseSecurityProviderSettings()
    )
    if not provider.base_url:
        raise ValueError(f"{identity} pfSense API URL is not configured")
    if not provider.api_key:
        raise ValueError(f"{identity} pfSense API key is not configured")
    return IdentitySettings(
        base_url=provider.base_url,
        api_key=provider.api_key,
        verify_ssl=provider.verify_ssl,
    )


def _args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the deployed pfSense posture/security keys without printing "
            "credential material."
        ),
    )
    parser.add_argument(
        "--url",
        help=(
            "Override transport URL for both identities, e.g. "
            "https://172.17.0.1:10443. Keys still come from the runtime environment."
        ),
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable certificate validation for a direct-IP transport comparison.",
    )
    return parser.parse_args(argv)


def _probe_identity(
    identity: Literal["posture", "security"],
    settings: IdentitySettings,
    *,
    override_url: str | None,
    insecure: bool,
) -> tuple[int, int]:
    expectations = [row for row in EXPECTATIONS if row.identity == identity]
    base_url = (override_url or settings.base_url).rstrip("/")
    verify_ssl = False if insecure else settings.verify_ssl
    passed = 0

    print(
        f"identity={identity} target={base_url} verify_ssl={str(verify_ssl).lower()} "
        f"key_present=yes",
    )
    timeout = httpx.Timeout(connect=3.0, read=6.0, write=3.0, pool=3.0)
    with httpx.Client(
        base_url=base_url,
        headers={"X-API-Key": settings.api_key, "Accept": "application/json"},
        timeout=timeout,
        follow_redirects=False,
        verify=verify_ssl,
    ) as client:
        for expectation in expectations:
            try:
                response = client.get(expectation.endpoint)
            except httpx.HTTPError as exc:
                print(
                    f"identity={identity} endpoint={expectation.endpoint} "
                    f"expected={expectation.expected_status} result=transport_error "
                    f"error={exc.__class__.__name__}",
                )
                continue

            ok = response.status_code == expectation.expected_status
            passed += int(ok)
            print(
                f"identity={identity} endpoint={expectation.endpoint} "
                f"expected={expectation.expected_status} actual={response.status_code} "
                f"result={'ok' if ok else 'mismatch'}",
            )

    return passed, len(expectations)


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    if args.url and not args.url.startswith("https://"):
        print("ERROR: --url must use https://", file=sys.stderr)
        return 2

    totals = [0, 0]
    for identity in ("posture", "security"):
        try:
            settings = _settings(identity)
        except (ValidationError, ValueError) as exc:
            print(
                f"identity={identity} result=configuration_error "
                f"error={exc.__class__.__name__}",
            )
            totals[1] += len(
                [row for row in EXPECTATIONS if row.identity == identity],
            )
            continue

        passed, expected = _probe_identity(
            identity,
            settings,
            override_url=args.url,
            insecure=args.insecure,
        )
        totals[0] += passed
        totals[1] += expected

    print(f"summary passed={totals[0]} total={totals[1]} secrets_printed=no")
    return 0 if totals[0] == totals[1] else 1


if __name__ == "__main__":
    raise SystemExit(main())
