#!/usr/bin/env python3
"""Reject unsafe or malformed Trivy image evidence before CI publication."""

import json
import sys
from pathlib import Path

MAX_BYTES = 8_000_000


def validate(report: Path) -> None:
    if report.is_symlink() or not report.is_file():
        raise ValueError("missing or unsafe report")
    with report.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("report outside allowed size")
    data = json.loads(raw)
    if (
        not isinstance(data, dict)
        or data.get("SchemaVersion") != 2
        or not isinstance(data.get("Results"), list)
        or len(data["Results"]) > 1000
    ):
        raise ValueError("invalid Trivy schema")
    for result in data["Results"]:
        if not isinstance(result, dict):
            raise ValueError("invalid Trivy result")
        if result.get("Secrets") or result.get("Misconfigurations"):
            raise ValueError("private evidence must not be published")
        findings = result.get("Vulnerabilities") or []
        if not isinstance(findings, list) or len(findings) > 5000:
            raise ValueError("invalid Trivy findings")
        for finding in findings:
            if not isinstance(finding, dict) or not isinstance(finding.get("VulnerabilityID"), str):
                raise ValueError("invalid Trivy finding")


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: validate_trivy_handoff.py REPORT", file=sys.stderr)
        return 2
    try:
        validate(Path(sys.argv[1]))
    except (OSError, ValueError):
        # Never echo input, exception details, paths or scanner evidence.
        print("Trivy publication refused: invalid or private evidence", file=sys.stderr)
        return 1
    print("Trivy publication boundary validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
