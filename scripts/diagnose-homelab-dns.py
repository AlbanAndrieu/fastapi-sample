#!/usr/bin/env python3
"""Read-only split-DNS comparison from workstation or TrueNAS host.

Compare direct pfSense/Unbound answers to the operating system resolver.
This does not prove HTTP, TLS, Cloudflare Access or FastAPI application health.
"""
from __future__ import annotations

import argparse
import ipaddress
import shutil
import subprocess
import sys
import time


def ipv4_answers(text: str) -> list[str]:
    """Select valid IPv4 addresses from short dig or getent output."""
    addresses: set[str] = set()
    for line in text.splitlines():
        fields = line.split()
        # `dig +short` is one address per line; `getent ahostsv4` starts with it.
        for candidate in fields[:1]:
            try:
                address = ipaddress.ip_address(candidate)
            except ValueError:
                continue
            if isinstance(address, ipaddress.IPv4Address):
                addresses.add(str(address))
    return sorted(addresses)


def lookup(command: list[str], timeout: float) -> tuple[list[str] | None, str]:
    """None means no evidence; [] means query ran without an A answer."""
    if not shutil.which(command[0]):
        return None, f"{command[0]} unavailable"
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except OSError:
        return None, "command error"
    if result.returncode != 0:
        return None, f"command exited {result.returncode}"
    return ipv4_answers(result.stdout), "queried"


def classify_internal(
    direct: list[str] | None, system: list[str] | None, expected: str
) -> str:
    if direct is None or system is None:
        return "unverified"
    if expected not in direct:
        return "pfsense_record_mismatch"
    if expected not in system:
        return "system_resolver_mismatch"
    return "matched"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vantage", choices=("workstation", "truenas"), required=True)
    parser.add_argument("--resolver", default="172.17.0.1")
    parser.add_argument("--internal-name", default="sample.int.albandrieu.com")
    parser.add_argument("--public-name", default="sample.albandrieu.com")
    parser.add_argument("--expected-internal-ip", default="172.17.0.24")
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    try:
        ipaddress.IPv4Address(args.resolver)
        ipaddress.IPv4Address(args.expected_internal_ip)
    except ipaddress.AddressValueError:
        parser.error("resolver and expected internal IP must be IPv4")
    if not 0 < args.timeout <= 10:
        parser.error("timeout must be in (0, 10] seconds")
    print(
        f"Observer={args.vantage}; DNS server={args.resolver}; "
        f"expected internal A={args.expected_internal_ip} (declared)"
    )
    results: dict[str, tuple[list[str] | None, list[str] | None]] = {}
    for label, host in (("internal", args.internal_name), ("public", args.public_name)):
        # `+short` prints A answers only; an empty result is not proof of a
        # specific DNS failure mode (NXDOMAIN/SERVFAIL require a separate dig).
        direct_start = time.perf_counter()
        direct, direct_reason = lookup(
            ["dig", f"@{args.resolver}", host, "A", "+short", "+tries=1", "+time=2"],
            args.timeout,
        )
        direct_ms = (time.perf_counter() - direct_start) * 1000
        system_start = time.perf_counter()
        system, system_reason = lookup(["getent", "ahostsv4", host], args.timeout)
        system_ms = (time.perf_counter() - system_start) * 1000
        results[label] = direct, system
        direct_elapsed = f"{direct_ms:.1f}ms" if direct is not None else "unavailable"
        system_elapsed = f"{system_ms:.1f}ms" if system is not None else "unavailable"
        print(
            f"{label}: pfSense={direct if direct is not None else 'NOT_RUN'} "
            f"({direct_reason}, {direct_elapsed}); "
            f"system={system if system is not None else 'NOT_RUN'} "
            f"({system_reason}, {system_elapsed})"
        )
    direct_internal, system_internal = results["internal"]
    outcome = classify_internal(direct_internal, system_internal, args.expected_internal_ip)
    print(f"Internal DNS comparison={outcome}")
    print(
        "Public DNS A values can change behind Cloudflare; "
        "no fixed public IP is required."
    )
    print("DNS answers do not prove TCP, TLS, HTTP/API, WebSocket or origin health.")
    if args.strict and (
        outcome != "matched"
        or any(
            direct is None or not direct or system is None or not system
            for direct, system in results.values()
        )
    ):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
