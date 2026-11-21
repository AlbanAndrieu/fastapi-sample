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
    if not isinstance(data, dict) or data.get("SchemaVersion") != 2 or not isinstance(data.get("Results"), list) or len(data["Results"]) > 1000:
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


def _safe_component_class(target: object) -> str:
    """Classify evidence origin only; never return a raw target path."""
    if not isinstance(target, str):
        return "other"
    if "/.venv/" in target or "site-packages/" in target:
        return "python_dependencies"
    if target.startswith("code/jm-python/") or "/code/jm-python/" in target:
        return "application"
    return "other"


def _redacted_private_counts(report: Path) -> tuple[int, int, str]:
    """Safe incident triage: return counts and fixed component class, never evidence."""
    try:
        with report.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            return 0, 0, "size_limit"
        results = json.loads(raw).get("Results", [])
        if not isinstance(results, list):
            return 0, 0, "unknown"
        secret_hits = 0
        config_hits = 0
        sources: set[str] = set()
        for item in results[:1000]:
            if not isinstance(item, dict):
                continue
            secrets = item.get("Secrets")
            configs = item.get("Misconfigurations")
            if isinstance(secrets, list) and secrets:
                secret_hits += len(secrets)
                sources.add(_safe_component_class(item.get("Target")))
            if isinstance(configs, list):
                config_hits += len(configs)
        if len(sources) != 1:
            kind = "mixed_or_unknown"
        else:
            kind = next(iter(sources))
        return min(secret_hits, 10000), min(config_hits, 10000), kind
    except (OSError, ValueError, TypeError, AttributeError):
        return 0, 0, "unavailable"


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: validate_trivy_handoff.py REPORT", file=sys.stderr)
        return 2
    try:
        validate(Path(sys.argv[1]))
    except (OSError, ValueError) as exc:
        # Only fixed code identifiers are logged. Do not echo paths, contents,
        # secret matches, CVEs, artifact metadata or untrusted error strings.
        allowed = {
            "missing or unsafe report": "missing_or_unsafe",
            "report outside allowed size": "report_size_limit",
            "invalid Trivy schema": "invalid_schema",
            "invalid Trivy result": "invalid_result",
            "private evidence must not be published": "private_evidence",
            "invalid Trivy findings": "invalid_vulnerabilities",
            "invalid Trivy finding": "invalid_vulnerability",
        }
        reason = allowed.get(str(exc), "unclassified")
        if reason == "private_evidence":
            secrets, configs, component = _redacted_private_counts(Path(sys.argv[1]))
            print(
                f"Trivy private findings: secrets={secrets}; config={configs}; component={component}",
                file=sys.stderr,
            )
        print(f"Trivy publication refused: invalid or private evidence; reason={reason}", file=sys.stderr)
        return 1
    print("Trivy publication boundary validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
