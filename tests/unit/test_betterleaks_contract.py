"""Contracts for Betterleaks secret scanning and Gitleaks migration."""

from pathlib import Path
import tomllib

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_betterleaks_is_the_only_precommit_secret_scanner() -> None:
    config = yaml.safe_load(
        (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"),
    )
    repo = next(
        repo
        for repo in config["repos"]
        if repo["repo"] == "https://github.com/betterleaks/betterleaks"
    )

    assert repo["rev"] == "v1.9.0"
    assert len(repo["hooks"]) == 1
    assert repo["hooks"][0]["id"] == "betterleaks"
    assert repo["hooks"][0]["args"] == ["--config", ".gitleaks.toml"]
    assert all(
        "gitleaks" not in entry["repo"].casefold()
        for entry in config["repos"]
    )


def test_just_uses_betterleaks_with_existing_config() -> None:
    source = (ROOT / "justfile").read_text(encoding="utf-8")

    assert "betterleaks dir . --config .gitleaks.toml --redact" in source
    assert (
        "betterleaks git . --pre-commit --staged "
        "--config .gitleaks.toml --redact"
    ) in source


def test_mise_pins_stable_betterleaks_release() -> None:
    mise = tomllib.loads((ROOT / "mise.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((ROOT / "mise.lock").read_text(encoding="utf-8"))

    assert mise["tools"]["betterleaks"] == "1.9.0"
    assert lock["tools"]["betterleaks"][0]["version"] == "1.9.0"
    assert lock["tools"]["betterleaks"][0]["backend"] == (
        "aqua:betterleaks/betterleaks"
    )


def test_megalinter_uses_betterleaks_with_errors_enabled() -> None:
    config = yaml.safe_load((ROOT / ".mega-linter.yml").read_text(encoding="utf-8"))

    assert "REPOSITORY_BETTERLEAKS" in config["ENABLE_LINTERS"]
    assert "REPOSITORY_GITLEAKS" not in config["ENABLE_LINTERS"]
    assert config["REPOSITORY_BETTERLEAKS_CONFIG_FILE"] == ".gitleaks.toml"
    assert config["REPOSITORY_BETTERLEAKS_DISABLE_ERRORS"] is False


def test_previous_finding_exclusions_remain_available() -> None:
    config = tomllib.loads((ROOT / ".gitleaks.toml").read_text(encoding="utf-8"))

    assert config["extend"]["useDefault"] is True
    assert config["allowlist"]["regexes"]
    assert (ROOT / ".gitleaksignore").is_file()

def test_brew_installs_betterleaks_instead_of_gitleaks() -> None:
    packages = (ROOT / "Brewfile").read_text(encoding="utf-8").splitlines()

    assert 'brew "betterleaks"' in packages
    assert 'brew "gitleaks"' not in packages
