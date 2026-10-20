"""Offline validation of scanner reports; no network or external scanner."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


def load_script(file: str):
    path = Path(__file__).resolve().parents[2] / "scripts/security" / file
    spec = importlib.util.spec_from_file_location(file.removesuffix(".py"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_betterleaks_incomplete_report_blocks(monkeypatch, tmp_path: Path):
    scanner = load_script("run_security_scans.py")
    monkeypatch.setattr(scanner, "_tool", lambda name: name)
    monkeypatch.setattr(scanner, "_run", lambda args: None)
    report = tmp_path / "betterleaks.json"
    for payload in (
        {"schema_version": "1", "findings": [], "scan": {"state": "incomplete"}},
        {"schema_version": "1", "findings": [], "scan": {}},
        {"schema_version": "1", "findings": [{}], "scan": {"state": "complete"}},
    ):
        report.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(RuntimeError):
            scanner._betterleaks(tmp_path)
    report.write_text(json.dumps({"schema_version": "1", "findings": [], "scan": {"state": "complete"}}), encoding="utf-8")
    scanner._betterleaks(tmp_path)


def _checked_report(dojo, root: Path, kind: str) -> bytes:
    """Current importer contract: private file first, then schema guard."""
    dojo.private_dir(root)
    content = dojo.private_file(root / dojo.REPORTS[kind][0], max_size=dojo.MAX_REPORT_BYTES)
    dojo.validate_format(kind, content)
    return content


def test_dojo_rejects_unsafe_nuclei_report(tmp_path: Path):
    dojo = load_script("import_defectdojo.py")
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    (root / "fastapi-sample").mkdir(mode=0o700)
    report = root / dojo.REPORTS["nuclei"][0]
    report.write_text('{"info":{"severity":"high"}}\n', encoding="utf-8")
    report.chmod(0o600)
    assert _checked_report(dojo, root, "nuclei") == b'{"info":{"severity":"high"}}\n'
    report.write_text('{"unexpected":true}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="invalid Nuclei"):
        _checked_report(dojo, root, "nuclei")
    report.write_text('{"info":{"severity":"high"}}\n', encoding="utf-8")
    report.chmod(0o644)
    with pytest.raises(ValueError, match="private regular file"):
        _checked_report(dojo, root, "nuclei")


def test_dojo_blocks_trivy_secret_report(tmp_path: Path):
    dojo = load_script("import_defectdojo.py")
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    report = root / dojo.REPORTS["trivy"][0]
    report.write_text(json.dumps({"Results": [{"Secrets": [{"RuleID": "synthetic"}]}]}), encoding="utf-8")
    report.chmod(0o600)
    with pytest.raises(ValueError, match="secret evidence"):
        _checked_report(dojo, root, "trivy")
