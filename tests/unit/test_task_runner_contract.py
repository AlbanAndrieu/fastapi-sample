"""Contracts for the additive Just/Make task-runner migration."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = ROOT / "justfile"
MAKEFILE = ROOT / "Makefile"


def _justfile() -> str:
    return JUSTFILE.read_text(encoding="utf-8")


def test_justfile_and_makefile_coexist() -> None:
    assert JUSTFILE.is_file()
    assert MAKEFILE.is_file()


def test_just_quality_recipes_delegate_to_canonical_scripts() -> None:
    source = _justfile()

    assert "bash scripts/agent-quality-gate.sh --fix" in source
    assert "bash scripts/agent-quality-gate.sh" in source
    assert "bash scripts/agent-publish.sh" in source


def test_just_legacy_recipes_delegate_to_make() -> None:
    source = _justfile()

    assert "make help" in source
    assert "make doc" in source
    assert "make build-docker" in source
    assert 'make "{{target}}"' in source


def test_justfile_does_not_replace_makefile() -> None:
    source = _justfile().casefold()

    assert "keep makefile" in source
    assert "legacy" in source


def test_makefile_keeps_bridges_to_just() -> None:
    source = MAKEFILE.read_text(encoding="utf-8")

    assert "just-help:" in source
    assert "just-fix:" in source
    assert "just-quality:" in source
    assert "just-publish-check:" in source
    assert "\tjust --list" in source
    assert "\tjust fix" in source
    assert "\tjust quality" in source
    assert "\tjust publish-check" in source
