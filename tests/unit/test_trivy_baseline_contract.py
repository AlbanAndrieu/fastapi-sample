"""Contracts for the triaged, blocking Trivy repository baseline."""

from pathlib import Path
import json
import re
import shlex

import yaml


ROOT = Path(__file__).resolve().parents[2]


def _megalinter_config() -> dict:
    return yaml.safe_load(
        (ROOT / ".mega-linter.yml").read_text(encoding="utf-8"),
    )


def _script_trivy_args() -> list[str]:
    source = (ROOT / "scripts" / "run-trivy.sh").read_text(encoding="utf-8")
    match = re.search(r"^TRIVY_ARGS=\((.*?)^\)", source, re.M | re.S)
    assert match is not None
    return shlex.split(match.group(1))


def test_megalinter_trivy_findings_are_blocking() -> None:
    config = _megalinter_config()

    assert "REPOSITORY_TRIVY" in config["ENABLE_LINTERS"]
    assert config["REPOSITORY_TRIVY_DISABLE_ERRORS"] is False


def test_local_trivy_script_reproduces_megalinter_scope() -> None:
    megalinter_args = shlex.split(
        _megalinter_config()["REPOSITORY_TRIVY_ARGUMENTS"],
    )
    source = (ROOT / "scripts" / "run-trivy.sh").read_text(encoding="utf-8")

    assert _script_trivy_args() == megalinter_args
    assert "--ignorefile" in megalinter_args
    assert "--skip-files" in megalinter_args
    assert "uv.lock" not in megalinter_args
    assert "package-lock.json" not in megalinter_args
    assert "--ignore-unfixed" not in megalinter_args
    assert "--exit-code 1" in source
    assert "exit 0" not in source


def test_trivyignore_has_no_unscoped_vulnerability_suppression() -> None:
    ignore = yaml.safe_load(
        (ROOT / ".trivyignore.yaml").read_text(encoding="utf-8"),
    )

    # Exceptions must never disable the scanner or apply to other artifacts.
    # The companion npm-bundle test enforces exact CVEs, purls and expiry.
    for entry in ignore["vulnerabilities"]:
        assert entry["paths"] == ["package-lock.json"]
        assert len(entry["purls"]) == 1
        assert entry["purls"][0].startswith("pkg:npm/")
        assert entry["expired_at"]
        assert entry["statement"]
    for entry in ignore["misconfigurations"]:
        assert entry["id"]


def test_smol_toml_override_excludes_known_vulnerable_releases() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    lock = json.loads(
        (ROOT / "package-lock.json").read_text(encoding="utf-8"),
    )

    assert package["overrides"]["smol-toml"] == "^1.9.0"
    installed = lock["packages"]["node_modules/smol-toml"]["version"]
    major, minor, _patch = (int(part) for part in installed.split("."))
    assert (major, minor) >= (1, 9)


def test_talos_stage_matches_image_uid_with_scoped_trivy_exceptions() -> None:
    manifest = yaml.safe_load_all((ROOT / "deploy/talos/fastapi-sample.yaml").read_text(encoding="utf-8"))
    deployment = next(x for x in manifest if x["kind"] == "Deployment")
    spec = deployment["spec"]["template"]["spec"]
    context = spec["securityContext"]
    assert context["runAsNonRoot"] is True
    assert context["runAsUser"] == 999  # Dockerfile USER 999:999
    assert context["runAsGroup"] == 999
    assert context["fsGroup"] == context["runAsGroup"]
    container = spec["containers"][0]
    assert container["image"].startswith("ghcr.io/albanandrieu/fastapi-sample@sha256:")
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    ignored = yaml.safe_load((ROOT / ".trivyignore.yaml").read_text(encoding="utf-8"))
    for risk in ("KSV-0020", "KSV-0021", "KSV-0125"):
        targeted = [x for x in ignored["misconfigurations"] if x["id"] == risk and "deploy/talos/fastapi-sample.yaml" in x.get("paths", [])]
        assert len(targeted) == 1
        assert targeted[0]["paths"] == ["deploy/talos/fastapi-sample.yaml"]
