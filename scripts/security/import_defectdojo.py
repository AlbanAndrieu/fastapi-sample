#!/usr/bin/env python3
"""Import a completed fastapi-sample security scan to LAN-only DefectDojo.

Dry-run has zero network/credential access. Apply requires an operator-approved
SHA-256, a complete master scan receipt and a protected API token file.
Never run as a GitHub-hosted job or expose DefectDojo to the Internet.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import ssl
import stat
import uuid

PROJECT = "fastapi-sample"
HOST = "defectdojo.int.albandrieu.com"
EDGE_IP = "172.17.0.24"
PORT = 443
ENDPOINT = "/api/v2/reimport-scan/"
MAX_REPORT_BYTES = 20 * 1024 * 1024
MAX_RECEIPT_BYTES = 8192
AUTHORIZED_SOURCES = ipaddress.ip_network("172.17.0.0/24")
REPORTS = {
    "trivy": ("trivy.json", "Trivy Scan"),
    "sbom": ("sbom.cdx.json", "CycloneDX Scan"),
    "zap": ("fastapi-sample/zap.json", "Zed Attack Proxy"),
    "nuclei": ("fastapi-sample/nuclei.jsonl", "Nuclei Scan"),
}
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
REVISION = re.compile(r"[0-9a-f]{40}\Z")


def private_file(path: Path, *, max_size: int) -> bytes:
    """Reject symlinks, group/world-readable data and oversized files."""
    if not path.is_absolute() or path.is_symlink():
        raise ValueError("private report must use an absolute non-symlink path")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            raise ValueError("report file must be a private regular file")
        if not 0 < info.st_size <= max_size:
            raise ValueError("missing or oversized private report")
        with os.fdopen(os.dup(fd), "rb") as stream:
            content = stream.read(max_size + 1)
        if len(content) != info.st_size:
            raise ValueError("report changed while reading")
        return content
    finally:
        os.close(fd)


def private_dir(path: Path) -> None:
    if path.is_symlink() or not path.is_dir() or path.stat().st_mode & 0o077:
        raise ValueError("report directory must be private (0700)")


def _validate_nuclei(content: bytes) -> None:
    for line in content.splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict) or not isinstance(item.get("info"), dict):
            raise ValueError("invalid Nuclei report")


def _validate_trivy(report: dict) -> None:
    results = report.get("Results")
    if not isinstance(results, list):
        raise ValueError("missing Trivy findings")
    if any(not isinstance(row, dict) or row.get("Secrets") for row in results):
        raise ValueError("Trivy secret evidence is forbidden for import")


def validate_format(kind: str, content: bytes) -> None:
    """Schema guard, not a substitute for scanner/parser acceptance."""
    if kind == "nuclei":
        _validate_nuclei(content)
        return
    report = json.loads(content)
    if not isinstance(report, dict):
        raise ValueError("invalid scanner report")
    if kind == "trivy":
        _validate_trivy(report)
    elif kind == "sbom":
        if report.get("bomFormat") != "CycloneDX":
            raise ValueError("invalid CycloneDX report")
    elif kind == "zap":
        if not isinstance(report.get("site"), list):
            raise ValueError("invalid ZAP report")


def validate_receipt(root: Path, kind: str, content: bytes) -> str:
    """Require evidence of a successfully completed master scan, with hash."""
    raw = private_file(root / "scan-receipt.json", max_size=MAX_RECEIPT_BYTES)
    receipt = json.loads(raw)
    if not isinstance(receipt, dict) or (
        receipt.get("schema_version") != 1
        or receipt.get("project") != PROJECT
        or receipt.get("mode") != "master"
        or receipt.get("state") != "complete"
        or not isinstance(receipt.get("revision"), str)
        or REVISION.fullmatch(receipt["revision"]) is None
        or not isinstance(receipt.get("reports"), dict)
        or receipt.get("policy_status") not in ("pass", "needs_review")
        or type(receipt.get("critical_count")) is not int
        or receipt["critical_count"] < 0
        or (receipt["critical_count"] > 0) != (receipt["policy_status"] == "needs_review")
    ):
        raise ValueError("missing complete master scan receipt")
    expected = receipt["reports"].get(REPORTS[kind][0])
    digest = hashlib.sha256(content).hexdigest()
    if expected != digest:
        raise ValueError("scan receipt digest mismatch")
    return digest


def approved_report(directory: Path, kind: str) -> tuple[bytes, str]:
    """Read only a named, complete report from one private project directory."""
    private_dir(directory)
    relative_path, _ = REPORTS[kind]
    path = directory / relative_path
    if path.parent != directory:
        private_dir(path.parent)
    content = private_file(path, max_size=MAX_REPORT_BYTES)
    validate_format(kind, content)
    return content, validate_receipt(directory, kind, content)


def multipart(content: bytes, kind: str, engagement_id: int) -> tuple[bytes, str]:
    boundary = "dojo-" + uuid.uuid4().hex
    fields = {
        "scan_type": REPORTS[kind][1],
        "engagement": str(engagement_id),
        "test_title": PROJECT + "-" + kind,
        "active": "true",
        "verified": "false",
        "auto_create_context": "false",
        "close_old_findings": "false",
        "minimum_severity": "Info",
    }
    output = bytearray()
    for key, value in fields.items():
        output.extend(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode(),
        )
    output.extend(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{Path(REPORTS[kind][0]).name}"\r\n'.encode(),
    )
    output.extend(b"Content-Type: application/octet-stream\r\n\r\n")
    output.extend(content)
    output.extend(f"\r\n--{boundary}--\r\n".encode())
    return bytes(output), boundary


class PinnedLANHTTPSConnection(http.client.HTTPSConnection):
    """Connect only to the private Traefik IP; verify TLS for the real FQDN."""

    def connect(self) -> None:
        raw_socket = socket.create_connection(
            (EDGE_IP, PORT),
            timeout=self.timeout,
            source_address=self.source_address,
        )
        try:
            # An unexpected source interface means this process is not using
            # the approved LAN path (e.g. container/VPN routing drift).
            if ipaddress.ip_address(raw_socket.getsockname()[0]) not in AUTHORIZED_SOURCES:
                raise RuntimeError("DefectDojo upload denied outside approved LAN")
            # The default HTTPSConnection SSLContext validates the certificate
            # using the hostname (not the pinned IP) as the TLS SNI/identity.
            self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)
        except Exception:
            raw_socket.close()
            raise


def submit(content: bytes, kind: str, engagement_id: int, token: str) -> str:
    if not ipaddress.ip_address(EDGE_IP).is_private:
        raise RuntimeError("Refusing non-private DefectDojo ingress")
    if not isinstance(engagement_id, int) or isinstance(engagement_id, bool) or engagement_id < 1:
        raise RuntimeError("A pre-existing positive engagement ID is required")
    if not token or "\r" in token or "\n" in token:
        raise RuntimeError("Invalid private import credential")
    body, boundary = multipart(content, kind, engagement_id)
    connection = PinnedLANHTTPSConnection(
        HOST,
        port=PORT,
        timeout=25,
        context=ssl.create_default_context(),
    )
    try:
        connection.request(
            "POST",
            ENDPOINT,
            body=body,
            headers={
                "Authorization": "Token " + token,
                "Content-Type": "multipart/form-data; boundary=" + boundary,
                "Content-Length": str(len(body)),
                "Accept": "application/json",
            },
        )
        response = connection.getresponse()
        # Never log raw response bodies: parser errors may echo finding data.
        raw = response.read(65537)
        if response.status not in (200, 201, 202) or len(raw) > 65536:
            raise RuntimeError("DefectDojo upload not accepted")
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("status") == "Failed":
            raise RuntimeError("DefectDojo returned invalid import status")
        if "engagement_id" in data and data["engagement_id"] != engagement_id:
            raise RuntimeError("DefectDojo engagement mismatch")
        # Accepted does not imply that Celery has finished processing findings.
        return "accepted_for_processing"
    except (OSError, ValueError, http.client.HTTPException):
        raise RuntimeError("Private DefectDojo HTTPS import failed (details redacted)") from None
    finally:
        connection.close()


def read_token() -> str:
    raw_path = os.environ.get("DD_FASTAPI_TOKEN_FILE", "")
    if not raw_path:
        raise RuntimeError("DD_FASTAPI_TOKEN_FILE required; do not pass raw tokens in env")
    path = Path(raw_path)
    if not path.is_absolute():
        raise RuntimeError("token path must be absolute")
    info = path.stat(follow_symlinks=False)
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) not in (0o600, 0o400):
        raise RuntimeError("token must belong to the importer and be mode 0400/0600")
    token = private_file(path, max_size=256).decode("ascii").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{24,128}", token):
        raise RuntimeError("invalid import token format")
    return token


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=sorted(REPORTS), required=True)
    parser.add_argument("--reports-dir", type=Path, required=True)
    parser.add_argument("--approved-sha256", help="SHA-256 independently approved by the operator")
    parser.add_argument("--apply", action="store_true", help="LAN-only authenticated import")
    args = parser.parse_args()
    # No symlink canonicalization before validation: callers must not disguise
    # a symlinked directory using resolve().
    root = args.reports_dir.absolute()
    content, digest = approved_report(root, args.kind)
    if not args.apply:
        print(f"CHECK OK: {PROJECT} {args.kind}, sha256={digest}; no network or secret read")
        return 0
    if not args.approved_sha256 or SHA256.fullmatch(args.approved_sha256) is None:
        raise RuntimeError("--approved-sha256 is required for actual upload")
    if digest != args.approved_sha256:
        raise RuntimeError("approved digest does not match the report")
    engagement_raw = os.environ.get("DD_FASTAPI_ENGAGEMENT_ID", "")
    if not engagement_raw.isdecimal() or int(engagement_raw) < 1:
        raise RuntimeError("existing DD_FASTAPI_ENGAGEMENT_ID is required")
    if os.environ.get("DD_IMPORT_APPROVED") != "YES":
        raise RuntimeError("DD_IMPORT_APPROVED=YES is required")
    token = read_token()
    status = submit(content, args.kind, int(engagement_raw), token)
    print(f"DefectDojo: {status}; confirm Celery processing and dedup privately")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
