"""Fail-closed producer-side report transport contracts."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "trivy_handoff",
    ROOT / "scripts/security/validate_trivy_handoff.py",
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize(
    "result",
    [{}, {"Vulnerabilities": [{"VulnerabilityID": "CVE-2026-0001"}]}],
)
def test_accept_native_report(tmp_path, result):
    report = tmp_path / "trivy.json"
    report.write_text(json.dumps({"SchemaVersion": 2, "Results": [result]}))
    module.validate(report)


@pytest.mark.parametrize(
    "result",
    [
        {"Secrets": [{"Match": "never publish"}]},
        {"Misconfigurations": [{"ID": "private config"}]},
        {"Vulnerabilities": [{"Severity": "HIGH"}]},
        {"Vulnerabilities": "invalid"},
    ],
)
def test_refuse_private_or_invalid_report(tmp_path, result):
    report = tmp_path / "trivy.json"
    report.write_text(json.dumps({"SchemaVersion": 2, "Results": [result]}))
    with pytest.raises(ValueError):
        module.validate(report)


def test_refuse_missing_or_oversized_report(tmp_path, monkeypatch):
    report = tmp_path / "trivy.json"
    with pytest.raises(ValueError):
        module.validate(report)
    monkeypatch.setattr(module, "MAX_BYTES", 2)
    report.write_text("{} ")
    with pytest.raises(ValueError):
        module.validate(report)


def test_publication_guard():
    workflow = (ROOT / ".github/workflows/docker-build.yml").read_text()
    assert "scanners: vuln\n" in workflow
    assert "scanners: secret\n" in workflow
    assert "output: trivy-secrets-private.json" in workflow
    secret_scanner = workflow.split("Run private Trivy image secret scan", 1)[1].split(
        "- name: Summarize private Trivy",
        1,
    )[0]
    assert "trivyignores: .trivyignore.yaml" in secret_scanner
    assert "validate_trivy_handoff.py trivy-secrets-private.json" in workflow
    assert workflow.index("Gate private Trivy secrets") < workflow.index("Convert same Trivy scan")
    assert "ignore-unfixed: false" in workflow
    assert workflow.count("steps.trivy_publication.outcome == 'success'") == 3
    assert workflow.index("validate_trivy_handoff.py") < workflow.index("trivy convert")


def test_docker_trivy_triage_is_metadata_only_and_fail_closed():
    workflow = (ROOT / ".github/workflows/docker-build.yml").read_text()
    first = workflow.index("Summarize private Trivy rule families without secret evidence")
    second = workflow.index("Gate private Trivy secrets without publication", first)
    snippet = workflow[first:second]
    assert "RuleID" in snippet
    assert "$safe_filename" in snippet
    assert "anthropic|claude" in snippet
    assert "site-packages/" in snippet
    assert "Match," not in snippet
    assert ".Match" not in snippet
    assert ".Code" not in snippet
    assert ".Message" not in snippet
    assert ".Target |" in snippet
    assert 'test("^[A-Za-z][A-Za-z0-9_.-]{0,63}$")' in snippet
    assert "validate_trivy_handoff.py trivy-secrets-private.json" in workflow[second:]


def test_private_evidence_diagnostics_never_expose_matches(tmp_path):
    report = tmp_path / "trivy.json"
    report.write_text(
        json.dumps(
            {
                "SchemaVersion": 2,
                "Results": [
                    {
                        "Target": "/code/.venv/lib/python3.13/site-packages/sample.py",
                        "Secrets": [{"Match": "CONFIDENTIAL_TOKEN_VALUE", "RuleID": "other"}],
                    },
                ],
            },
        ),
    )
    count, config, component = module._redacted_private_counts(report)
    assert (count, config, component) == (1, 0, "python_dependencies")
    assert "CONFIDENTIAL_TOKEN_VALUE" not in str((count, config, component))
