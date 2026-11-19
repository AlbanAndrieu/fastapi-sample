"""Bounded authenticated ZAP runner; publish only credential-free alert IDs."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[2]
ORIGIN = "https://fastapi-sample.albandrieu.com"
HOST_PATTERN = r"^https://fastapi-sample[.]albandrieu[.]com(?::443)?/.*$"
IMAGE = "ghcr.io/zaproxy/zaproxy:2.17.0"
TARGETS = {
    "root": ("/", "web", b'class="op-eyebrow"'),
    "api": ("/api", "web", b'id="health-board"'),
    "openapi": ("/openapi.json", "api", None),
}
KEYS = ("CF_ACCESS_CLIENT_ID", "CF_ACCESS_CLIENT_SECRET")
HEADERS = ("CF-Access-Client-Id", "CF-Access-Client-Secret")


class NoRedirect(HTTPRedirectHandler):
    """Credentials are never forwarded across an HTTP redirect."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def credentials() -> tuple[str, str]:
    values = tuple(os.environ.get(key, "") for key in KEYS)
    if not all(re.fullmatch(r"[A-Za-z0-9_.-]+", value) for value in values):
        raise ValueError("Access service token missing or malformed")
    return values[0], values[1]


def auth_properties(values: tuple[str, str]) -> str:
    """Both headers are scoped to exactly one HTTPS host."""
    lines = []
    for index, (header, value) in enumerate(zip(HEADERS, values, strict=True)):
        prefix = f"replacer.full_list({index})"
        lines.extend(
            [
                f"{prefix}.description=cloudflare-access-{index}",
                f"{prefix}.enabled=true",
                f"{prefix}.url={HOST_PATTERN}",
                f"{prefix}.matchtype=REQ_HEADER",
                f"{prefix}.matchstr={header}",
                f"{prefix}.regex=false",
                f"{prefix}.replacement={value}",
            ],
        )
    return "\n".join(lines) + "\n"


def preflight(values: tuple[str, str]) -> int:
    opener = build_opener(ProxyHandler({}), NoRedirect())
    for path, _, marker in TARGETS.values():
        try:
            request = Request(ORIGIN + path, headers=dict(zip(HEADERS, values, strict=True)))
            with opener.open(request, timeout=15) as response:
                if response.status != 200:
                    raise ValueError("unexpected HTTP status")
                data = response.read(2_000_001)
            if len(data) > 2_000_000:
                raise ValueError("response exceeds budget")
            if marker is not None:
                if marker not in data:
                    raise ValueError("HTML route marker missing")
            else:
                spec = json.loads(data)
                if not isinstance(spec.get("openapi"), str) or not isinstance(spec.get("paths"), dict):
                    raise ValueError("OpenAPI contract missing")
        except HTTPError as exc:
            print(f"DAST preflight {path}: HTTP {exc.code}")
            return 1
        except (URLError, TimeoutError, OSError, ValueError, TypeError, AttributeError):
            print(f"DAST preflight {path}: transport or application contract failed")
            return 1
        print(f"DAST preflight {path}: HTTP 200, application marker verified")
    return 0


def alert_summary(payload: dict) -> list[dict]:
    """Allowlist numeric scanner metadata only; no URI, evidence or raw headers."""
    rows = []
    expected_sites = [
        site
        for site in payload["site"]
        if site.get("@name") in (ORIGIN, ORIGIN + ":443")
    ]
    if not expected_sites:
        raise ValueError("no report for the expected target origin")
    for site in expected_sites:
        for alert in site["alerts"]:
            row = {
                "pluginId": int(alert["pluginid"]),
                "risk": int(alert["riskcode"]),
                "confidence": int(alert["confidence"]),
                "instances": int(alert.get("count", len(alert.get("instances", [])))),
            }
            if not (row["pluginId"] > 0 and 0 <= row["risk"] <= 3 and 0 <= row["confidence"] <= 4 and row["instances"] >= 0):
                raise ValueError("invalid alert metadata")
            rows.append(row)
    return rows


def scan(target: str, values: tuple[str, str]) -> int:
    path, kind, _ = TARGETS[target]
    report_dir = ROOT / "reports" / "dast"
    report_dir.mkdir(parents=True, exist_ok=True)
    result = {"target": target, "scanExitCode": 3, "reportState": "unavailable", "alerts": []}
    with tempfile.TemporaryDirectory(prefix="nabla-zap-") as directory:
        root = Path(directory)
        work = root / "work"
        work.mkdir()
        work.chmod(0o777)  # Bind-mounted writable directory on an ephemeral runner.
        config = root / "auth.properties"
        config.write_text(auth_properties(values), encoding="utf-8")
        config.chmod(0o444)  # Enclosing directory remains private; Docker mount is read-only.
        shutil.copyfile(ROOT / ".zap" / f"{kind}-rules.tsv", work / "rules.tsv")
        name = root.name
        command = [
            "docker", "run", "--rm", "--name", name, "--network", "bridge",
            "-v", f"{work}:/zap/wrk:rw", "-v", f"{config}:/zap-auth.properties:ro",
            IMAGE, "zap-baseline.py" if kind == "web" else "zap-api-scan.py",
            "-t", ORIGIN + path, "-c", "rules.tsv", "-J", "report.json",
            "-I", "-T", "4", "-s", "-z", "-configfile /zap-auth.properties",
        ]
        if kind == "api":
            command.extend(["-f", "openapi"])
        # Raw scanner output can contain credentials or application responses.
        # Never stream it to GitHub logs or upload its raw reports.
        try:
            completed = subprocess.run(
                command, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=480,
            )
            result["scanExitCode"] = completed.returncode
            raw = work / "report.json"
            if raw.stat().st_size > 20_000_000:
                raise ValueError("report exceeds budget")
            result["alerts"] = alert_summary(json.loads(raw.read_text(encoding="utf-8")))
            result["reportState"] = "sanitized"
        except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
            result["reportState"] = "unavailable"
        finally:
            try:
                subprocess.run(
                    ["docker", "rm", "-f", name],
                    check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
                )
            except (OSError, subprocess.TimeoutExpired):
                result["reportState"] = "unavailable"
    (report_dir / f"{target}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"DAST {target}: exit={result['scanExitCode']} report={result['reportState']} alerts={len(result['alerts'])}")
    if result["reportState"] != "sanitized":
        return 3
    return int(result["scanExitCode"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=("preflight", *TARGETS))
    args = parser.parse_args()
    try:
        values = credentials()
    except ValueError:
        print("DAST Access credentials missing or malformed")
        return 2
    return preflight(values) if args.target == "preflight" else scan(args.target, values)


if __name__ == "__main__":
    raise SystemExit(main())
