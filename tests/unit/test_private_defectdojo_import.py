"""Offline security contracts for LAN-only DefectDojo import."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/security/import_defectdojo.py"
spec = importlib.util.spec_from_file_location("import_defectdojo", SCRIPT)
assert spec is not None and spec.loader is not None
dojo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dojo)


@pytest.fixture
def complete_report(tmp_path: Path) -> tuple[Path, str]:
    tmp_path.chmod(0o700)
    report = tmp_path / "trivy.json"
    content = json.dumps({"Results": []}).encode()
    report.write_bytes(content)
    report.chmod(0o600)
    digest = hashlib.sha256(content).hexdigest()
    receipt = {
        "schema_version": 1,
        "project": "fastapi-sample",
        "mode": "master",
        "state": "complete",
        "policy_status": "pass",
        "critical_count": 0,
        "revision": "a" * 40,
        "reports": {"trivy.json": digest},
    }
    file = tmp_path / "scan-receipt.json"
    file.write_text(json.dumps(receipt), encoding="utf-8")
    file.chmod(0o600)
    return tmp_path, digest


def test_validated_report_dry_run_never_needs_a_token(
    complete_report: tuple[Path, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder, digest = complete_report
    monkeypatch.delenv("DD_FASTAPI_TOKEN_FILE", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        ["import_defectdojo.py", "--kind", "trivy", "--reports-dir", str(folder)],
    )
    assert dojo.main() == 0
    raw, observed = dojo.approved_report(folder, "trivy")
    assert observed == digest
    assert json.loads(raw) == {"Results": []}


def test_import_rejects_absent_or_mismatched_receipt(
    complete_report: tuple[Path, str],
) -> None:
    folder, _ = complete_report
    (folder / "scan-receipt.json").unlink()
    with pytest.raises(FileNotFoundError):
        dojo.approved_report(folder, "trivy")

    receipt = {
        "schema_version": 1,
        "project": "fastapi-sample",
        "mode": "pr",
        "state": "complete",
        "policy_status": "pass",
        "critical_count": 0,
        "revision": "a" * 40,
        "reports": {"trivy.json": "f" * 64},
    }
    path = folder / "scan-receipt.json"
    path.write_text(json.dumps(receipt))
    path.chmod(0o600)
    with pytest.raises(ValueError, match="complete master"):
        dojo.approved_report(folder, "trivy")
    receipt["mode"] = "master"
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="digest mismatch"):
        dojo.approved_report(folder, "trivy")


def test_secret_report_and_world_readable_file_are_rejected(
    complete_report: tuple[Path, str],
) -> None:
    folder, _ = complete_report
    report = folder / "trivy.json"
    report.write_text(json.dumps({"Results": [{"Secrets": [{"Target": "fixture"}]}]}))
    with pytest.raises(ValueError, match="secret evidence"):
        dojo.approved_report(folder, "trivy")
    report.chmod(0o644)
    with pytest.raises(ValueError, match="private regular"):
        dojo.approved_report(folder, "trivy")


def test_symlinked_reports_and_directories_are_rejected(
    complete_report: tuple[Path, str],
    tmp_path: Path,
) -> None:
    folder, _ = complete_report
    link = tmp_path.parent / (tmp_path.name + "-link")
    link.symlink_to(folder, target_is_directory=True)
    try:
        with pytest.raises(ValueError, match="directory must be private"):
            dojo.approved_report(link, "trivy")
    finally:
        link.unlink()


def test_apply_requires_independent_digest_before_token_read(
    complete_report: tuple[Path, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder, digest = complete_report
    monkeypatch.setenv("DD_FASTAPI_ENGAGEMENT_ID", "42")
    monkeypatch.setenv("DD_IMPORT_APPROVED", "YES")
    attempts = []
    monkeypatch.setattr(dojo, "read_token", lambda: attempts.append("token") or "tokenfixture1234567890123456")
    monkeypatch.setattr(
        dojo,
        "submit",
        lambda content, kind, engagement, token: attempts.append((kind, engagement, token)) or "accepted_for_processing",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "import_defectdojo.py",
            "--kind",
            "trivy",
            "--reports-dir",
            str(folder),
            "--apply",
            "--approved-sha256",
            "0" * 64,
        ],
    )
    with pytest.raises(RuntimeError, match="approved digest"):
        dojo.main()
    assert attempts == []
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "import_defectdojo.py",
            "--kind",
            "trivy",
            "--reports-dir",
            str(folder),
            "--apply",
            "--approved-sha256",
            digest,
        ],
    )
    assert dojo.main() == 0
    assert attempts == ["token", ("trivy", 42, "tokenfixture1234567890123456")]


def test_fixed_private_https_target_and_same_origin_tls_sni(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: list[object] = []

    class FakeSocket:
        def getsockname(self):
            return ("172.17.0.57", 48123)

        def close(self) -> None:
            observed.append("closed")

    class FakeContext:
        def wrap_socket(self, sock, *, server_hostname: str):
            observed.append(("sni", server_hostname))
            return sock

    def connect(address, timeout, source_address=None):
        observed.append(("peer", address))
        return FakeSocket()

    monkeypatch.setattr(dojo.socket, "create_connection", connect)
    connection = dojo.PinnedLANHTTPSConnection(
        dojo.HOST,
        port=dojo.PORT,
        context=FakeContext(),
        timeout=1,
    )
    connection.connect()
    assert observed == [
        ("peer", ("172.17.0.24", 443)),
        ("sni", "defectdojo.int.albandrieu.com"),
    ]
    connection.close()


def test_multipart_cannot_autocreate_and_is_scoped_by_scan_type() -> None:
    body, boundary = dojo.multipart(b'{"Results":[]}', "trivy", 42)
    assert boundary.encode() in body
    assert b'auto_create_context"\r\n\r\nfalse' in body
    assert b'close_old_findings"\r\n\r\nfalse' in body
    assert b'test_title"\r\n\r\nfastapi-sample-trivy' in body
    assert b'engagement"\r\n\r\n42' in body


def test_private_tls_rejects_non_lan_source_even_if_destination_private(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BadSource:
        def getsockname(self):
            return ("10.254.255.9", 1234)

        def close(self):
            pass

    class StubContext:
        def wrap_socket(self, *args, **kwargs):
            raise AssertionError("TLS must not begin from an unauthorized source")

    monkeypatch.setattr(
        dojo.socket,
        "create_connection",
        lambda address, timeout, source_address=None: BadSource(),
    )
    conn = dojo.PinnedLANHTTPSConnection(
        dojo.HOST,
        port=dojo.PORT,
        context=StubContext(),
        timeout=1,
    )
    with pytest.raises(RuntimeError, match="outside approved LAN"):
        conn.connect()


def test_submit_rejects_invalid_engagement_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dojo, "PinnedLANHTTPSConnection", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network forbidden")))
    for engagement in (0, -1, True):
        with pytest.raises(RuntimeError, match="engagement ID"):
            dojo.submit(b'{"Results":[]}', "trivy", engagement, "fixture-token")
    with pytest.raises(RuntimeError, match="credential"):
        dojo.submit(b'{"Results":[]}', "trivy", 42, "bad\r\nInjected: header")
