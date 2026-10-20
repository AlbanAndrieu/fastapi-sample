"""Offline tests for completed, private, master-only scanner receipts."""

from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/security/run_security_scans.py"
spec = importlib.util.spec_from_file_location("private_scans", SCRIPT)
assert spec is not None and spec.loader is not None
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)


@pytest.fixture
def reports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(scan, "ROOT", tmp_path)
    data = {
        "betterleaks.json": b'{"schema_version":"1","findings":[],"scan":{"state":"complete"}}',
        "trivy.json": b'{"Results":[]}',
        "sbom.cdx.json": b'{"bomFormat":"CycloneDX"}',
        "semgrep.json": b'{"results":[]}',
        "trivy.sarif": b'{"version":"2.1.0","runs":[]}',
        "licenses-full.json": b'{"Results":[]}',
    }
    for name, contents in data.items():
        file = tmp_path / name
        file.write_bytes(contents)
        file.chmod(0o600)
    return tmp_path


def fake_git(revision: str, master: str):
    def run(command, **_kwargs):
        ref = command[-1]
        if ref == "HEAD":
            return CompletedProcess(command, 0, revision + "\n", "")
        if ref == "refs/remotes/origin/master":
            return CompletedProcess(command, 0, master + "\n", "")
        return CompletedProcess(command, 1, "", "")

    return run


def test_master_receipt_contains_reproducible_hashes_and_no_report_contents(
    reports: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = "a" * 40
    monkeypatch.setattr(scan.subprocess, "run", fake_git(revision, revision))
    scan._write_completed_receipt(reports, mode="master", dast=False)
    saved = json.loads((reports / "scan-receipt.json").read_text())
    assert saved["schema_version"] == 1
    assert saved["project"] == "fastapi-sample"
    assert saved["mode"] == "master"
    assert saved["state"] == "complete"
    assert saved["revision"] == revision
    assert (
        saved["reports"]["trivy.json"]
        == sha256(
            (reports / "trivy.json").read_bytes(),
        ).hexdigest()
    )
    assert "betterleaks.json" in saved["reports"]
    assert "licenses-full.json" in saved["reports"]
    assert "semgrep.json" in saved["reports"]


def test_master_receipt_rejects_non_master_commit(
    reports: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scan.subprocess, "run", fake_git("b" * 40, "a" * 40))
    with pytest.raises(RuntimeError, match="verified master ref"):
        scan._write_completed_receipt(reports, mode="master", dast=False)
    assert not (reports / "scan-receipt.json").exists()


def test_zero_findings_nuclei_is_a_completed_scan_not_missing_report(
    reports: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = "a" * 40
    monkeypatch.setattr(scan.subprocess, "run", fake_git(revision, revision))
    dast = reports / "fastapi-sample"
    dast.mkdir()
    (dast / "zap.json").write_text('{"site":[]}')
    (dast / "nuclei.jsonl").write_bytes(b"")
    scan._write_completed_receipt(reports, mode="master", dast=True)
    receipt = json.loads((reports / "scan-receipt.json").read_text())
    assert receipt["reports"]["fastapi-sample/nuclei.jsonl"] == sha256(b"").hexdigest()


def test_missing_requested_report_fails_instead_of_producing_success_receipt(
    reports: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = "a" * 40
    monkeypatch.setattr(scan.subprocess, "run", fake_git(revision, revision))
    (reports / "semgrep.json").unlink()
    with pytest.raises(RuntimeError, match="report is missing"):
        scan._write_completed_receipt(reports, mode="master", dast=False)
    assert not (reports / "scan-receipt.json").exists()


def test_master_critical_findings_record_complete_but_failing_policy(
    reports: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = "a" * 40
    monkeypatch.setattr(scan.subprocess, "run", fake_git(revision, revision))
    scan._write_completed_receipt(reports, mode="master", dast=False, critical=2)
    receipt = json.loads((reports / "scan-receipt.json").read_text())
    assert receipt["state"] == "complete"
    assert receipt["policy_status"] == "needs_review"
    assert receipt["critical_count"] == 2


def test_optional_sarif_is_hashed_without_new_scan(
    reports: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = "a" * 40
    monkeypatch.setattr(scan.subprocess, "run", fake_git(revision, revision))
    scan._write_completed_receipt(
        reports,
        mode="master",
        dast=False,
        sarif=True,
    )
    receipt = json.loads((reports / "scan-receipt.json").read_text())
    assert (
        receipt["reports"]["trivy.sarif"]
        == sha256(
            (reports / "trivy.sarif").read_bytes(),
        ).hexdigest()
    )


def test_sarif_conversion_is_a_format_transform_not_rescan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []

    def fake_run(args: list[str], **_kwargs) -> None:
        commands.append(args)
        (tmp_path / "trivy.sarif").write_text('{"version":"2.1.0","runs":[]}')

    monkeypatch.setattr(scan, "_run", fake_run)
    monkeypatch.setattr(scan, "_tool", lambda _name: "trivy")
    scan._trivy_sarif(tmp_path)
    assert len(commands) == 1
    assert commands[0][1:4] == ["convert", "--format", "sarif"]
    assert commands[0][-1] == str(tmp_path / "trivy.json")
