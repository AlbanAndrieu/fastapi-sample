#!/usr/bin/env python3
"""Local-first security evidence; DAST only with explicit master opt-in.

Never upload unredacted secret findings. Do not run active scans on pull
requests. Output is private and must not be committed as a build artifact.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import re
import tempfile

ROOT = Path(__file__).resolve().parents[2]
OWNED_TARGETS = ("https://fastapi-sample.fastapicloud.dev/",)


def _tool(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        raise RuntimeError(f"required security tool unavailable: {name}")
    return found


def _run(args: list[str], *, cwd: Path = ROOT) -> None:
    # Diagnostics may contain secrets, so do not echo scanner stdout/stderr.
    result = subprocess.run(args, cwd=cwd, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"security tool failed: {Path(args[0]).name} (exit {result.returncode})")


def critical_findings(report: dict) -> tuple[int, int]:
    """Count CRITICAL/secret findings without reproducing vulnerable evidence."""
    if not isinstance(report, dict) or not isinstance(report.get("Results"), list):
        raise ValueError("Trivy report missing Results")
    critical = secrets = 0
    for result in report["Results"]:
        if not isinstance(result, dict):
            raise ValueError("invalid Trivy result")
        for field in ("Vulnerabilities", "Misconfigurations", "Licenses"):
            for finding in result.get(field) or []:
                if str(finding.get("Severity", "")).upper() == "CRITICAL":
                    critical += 1
        secrets += len(result.get("Secrets") or [])
    return critical, secrets


def _trivy(path: Path, *, deep: bool = False, block_critical: bool = True) -> int:
    args = [
        _tool("trivy"),
        "fs",
        "--skip-version-check",
        "--scanners",
        "vuln,misconfig,secret,license",
        "--vuln-type",
        "os,library",
        "--ignorefile",
        ".trivyignore.yaml",
        "--skip-dirs",
        ".venv",
        "--skip-dirs",
        "node_modules",
        "--skip-dirs",
        "megalinter-reports",
        "--skip-dirs",
        ".direnv",
        "--skip-dirs",
        "open-webui",
        "--skip-files",
        "trivy-sbom.json",
        "--format",
        "json",
        "--output",
        str(path / "trivy.json"),
        ".",
    ]
    # Intentionally DOES NOT exclude uv.lock / package-lock.json or hide
    # unfixable critical findings.
    _run(args)
    report = json.loads((path / "trivy.json").read_text(encoding="utf-8"))
    critical, secrets = critical_findings(report)
    print(f"Trivy summary: critical={critical} secrets={secrets}")
    # A completed master scan may contain Critical findings worth triaging in
    # DefectDojo; they still produce a nonzero *policy* verdict after receipt.
    # Secrets never generate an import-approved receipt.
    if secrets or (critical and block_critical):
        raise RuntimeError("Trivy blocking findings (see private report)")
    _run(
        [
            _tool("trivy"),
            "fs",
            "--skip-version-check",
            "--scanners",
            "vuln",
            "--format",
            "cyclonedx",
            "--output",
            str(path / "sbom.cdx.json"),
            ".",
        ],
    )
    if deep:
        # Extended filesystem license classification is CPU-expensive: master only.
        _run(
            [
                _tool("trivy"),
                "fs",
                "--scanners",
                "license",
                "--license-full",
                "--format",
                "json",
                "--output",
                str(path / "licenses-full.json"),
                ".",
            ],
        )
        licenses = json.loads((path / "licenses-full.json").read_text(encoding="utf-8"))
        violations, _secrets = critical_findings(licenses)
        if violations:
            raise RuntimeError("forbidden licenses in private master report")
    return critical


def _trivy_sarif(path: Path) -> None:
    """Convert the completed private Trivy JSON once; no second scanner run."""
    _run(
        [
            _tool("trivy"),
            "convert",
            "--format",
            "sarif",
            "--output",
            str(path / "trivy.sarif"),
            str(path / "trivy.json"),
        ],
    )
    sarif = json.loads((path / "trivy.sarif").read_text(encoding="utf-8"))
    if not isinstance(sarif, dict) or sarif.get("version") != "2.1.0" or not isinstance(sarif.get("runs"), list):
        raise RuntimeError("Trivy SARIF is missing or malformed")


def _betterleaks(path: Path) -> None:
    _run(
        [
            _tool("betterleaks"),
            "filesystem",
            ".",
            "--config",
            ".gitleaks.toml",
            "--redact=100",
            "--output",
            str(path / "betterleaks.json"),
        ],
    )
    data = json.loads((path / "betterleaks.json").read_text(encoding="utf-8"))
    if (
        not isinstance(data, dict)
        or data.get("schema_version") != "1"
        or not isinstance(data.get("findings"), list)
        or not isinstance(data.get("scan"), dict)
        or data["scan"].get("state") != "complete"
    ):
        raise RuntimeError("betterleaks report missing or incomplete")
    if data["findings"]:
        raise RuntimeError("secret leaks detected; report retained privately")
    print("Betterleaks: no findings")


def _semgrep(path: Path) -> None:
    _run(
        [
            _tool("semgrep"),
            "scan",
            "--metrics=off",
            "--config",
            "auto",
            "--json",
            "--output",
            str(path / "semgrep.json"),
            ".",
        ],
    )


def _dast(path: Path) -> None:
    # Only two explicitly approved hosts; no wildcard, no authenticated
    # admin, no active ZAP API scanner and no high-rate Nuclei.
    for label, target in zip(("fastapi-sample",), OWNED_TARGETS, strict=True):
        folder = path / label
        folder.mkdir(mode=0o700, exist_ok=True)
        _run(
            [
                _tool("docker"),
                "run",
                "--rm",
                "--network",
                "bridge",
                "-v",
                f"{folder}:/zap/wrk:rw",
                "ghcr.io/zaproxy/zaproxy:2.17.0",
                "zap-baseline.py",
                "-t",
                target,
                "-m",
                "2",
                "-I",
                "-J",
                "zap.json",
            ],
        )
        _run(
            [
                _tool("nuclei"),
                "-u",
                target,
                "-severity",
                "high,critical",
                "-etags",
                "dos,fuzz,headless",
                "-rl",
                "1",
                "-c",
                "1",
                "-timeout",
                "5",
                "-retries",
                "0",
                "-jsonl",
                "-o",
                str(folder / "nuclei.jsonl"),
            ],
        )
        zap = json.loads((folder / "zap.json").read_text(encoding="utf-8"))
        alerts = [alert for site in zap.get("site", []) for alert in site.get("alerts", [])]
        if any(int(alert.get("riskcode", 0)) >= 3 for alert in alerts):
            raise RuntimeError(f"ZAP high-risk findings in {label} private report")
        nuclei_report = folder / "nuclei.jsonl"
        if not nuclei_report.is_file():
            raise RuntimeError("Nuclei did not produce its report")
        if any(json.loads(line).get("info", {}).get("severity", "").lower() == "critical" for line in nuclei_report.read_text(encoding="utf-8").splitlines() if line.strip()):
            raise RuntimeError(f"Nuclei critical findings in {label} private report")


def _write_completed_receipt(
    folder: Path,
    *,
    mode: str,
    dast: bool,
    critical: int = 0,
    sarif: bool = False,
) -> None:
    """Emit checksums only after every requested scanner succeeds."""
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise RuntimeError("security scan requires an immutable git SHA")
    names = ["betterleaks.json", "trivy.json", "sbom.cdx.json"]
    if sarif:
        names.append("trivy.sarif")
    if mode == "master":
        refs = ("refs/remotes/origin/master", "refs/heads/master")
        master_shas = {
            result.stdout.strip()
            for ref in refs
            if (
                result := subprocess.run(
                    ["git", "rev-parse", "--verify", ref],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            ).returncode
            == 0
        }
        if revision not in master_shas:
            raise RuntimeError("master scan requires HEAD equal to a verified master ref")
        names.extend(("semgrep.json", "licenses-full.json"))
    if dast:
        names.extend(("fastapi-sample/zap.json", "fastapi-sample/nuclei.jsonl"))
    reports: dict[str, str] = {}
    for relative in names:
        file = folder / relative
        if not file.is_file() or file.is_symlink():
            raise RuntimeError("complete security scan report is missing")
        # Successful Nuclei runs with zero findings legitimately emit empty JSONL.
        if file.stat().st_size == 0 and relative != "fastapi-sample/nuclei.jsonl":
            raise RuntimeError("complete security scan report is missing")
        reports[relative] = hashlib.sha256(file.read_bytes()).hexdigest()
    receipt = {
        "schema_version": 1,
        "project": "fastapi-sample",
        "mode": mode,
        "state": "complete",
        # Completeness is not a claim that no security findings were detected.
        "policy_status": "needs_review" if critical else "pass",
        "critical_count": critical,
        "revision": revision,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "reports": reports,
    }
    # Scanner output stays private, not a GitHub Actions artifact.
    (folder / "scan-receipt.json").write_text(
        json.dumps(receipt, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("pr", "master"), default="pr")
    parser.add_argument("--dast", action="store_true")
    parser.add_argument(
        "--sarif",
        action="store_true",
        help="convert Trivy JSON to private SARIF without a second scan",
    )
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.dast and args.mode != "master":
        parser.error("DAST is forbidden in PR mode")
    # Apply privacy constraints before tempfile, mkdir or scanner execution.
    os.umask(0o077)
    if args.output_dir is None:
        out = Path(tempfile.mkdtemp(prefix="fastapi-security-")).resolve()
    else:
        out = args.output_dir.resolve()
        if out.is_relative_to(ROOT):
            parser.error("reports must stay outside the repository")
        out.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Restrictive umask must apply before the *first* report/output file.
    # chmod additionally repairs an existing directory supplied by caller.
    os.chmod(out, 0o700)
    # Reusing a directory could promote stale reports into a new receipt.
    if any(out.iterdir()):
        parser.error("security report directory must be empty for a new scan")
    print(f"Private scan directory: {out}")
    _betterleaks(out)
    critical = _trivy(
        out,
        deep=args.mode == "master",
        block_critical=args.mode != "master",
    )
    if args.sarif:
        _trivy_sarif(out)
    if args.mode == "master":
        _semgrep(out)
        if args.dast:
            _dast(out)
    _write_completed_receipt(
        out,
        mode=args.mode,
        dast=args.dast,
        critical=critical,
        sarif=args.sarif,
    )
    if critical:
        # Preserve completed master evidence for explicitly approved private
        # DefectDojo triage, but never disguise the security gate as green.
        raise RuntimeError("Critical findings require triage; scan receipt is complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
