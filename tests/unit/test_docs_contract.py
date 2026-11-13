"""Unit contracts for repository-local Markdown links."""

from pathlib import Path

from scripts.check_docs_links import default_markdown_files, resolve_local_target, validate_markdown


def test_validate_markdown_accepts_existing_local_external_and_anchor_links(
    tmp_path: Path,
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    target = docs / "target.md"
    target.write_text("# Target\n", encoding="utf-8")
    source = docs / "source.md"
    source.write_text(
        "\n".join(
            (
                "[relative](target.md)",
                "[fragment](target.md#section)",
                "[anchor](#local)",
                "[external](https://example.com/path)",
            ),
        )
        + "\n",
        encoding="utf-8",
    )

    assert validate_markdown(source, tmp_path) == []


def test_validate_markdown_reports_missing_and_escaping_targets(
    tmp_path: Path,
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    source = docs / "source.md"
    source.write_text(
        "[missing](missing.md)\n[escape](../../outside.md)\n",
        encoding="utf-8",
    )

    errors = validate_markdown(source, tmp_path)

    assert any("missing local target: docs/missing.md" in error for error in errors)
    assert any("link escapes repository: ../../outside.md" in error for error in errors)


def test_resolve_local_target_ignores_non_file_links(tmp_path: Path) -> None:
    source = tmp_path / "README.md"

    assert resolve_local_target(source, "#section", tmp_path) is None
    assert resolve_local_target(source, "mailto:test@example.com", tmp_path) is None
    assert resolve_local_target(source, "https://example.com", tmp_path) is None


def test_active_only_excludes_archive_without_changing_full_contract(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    archive = docs / "archive" / "2026-10-29"
    archive.mkdir(parents=True)
    active = docs / "current.md"
    active.write_text("# Current\n", encoding="utf-8")
    historical = archive / "historical.md"
    historical.write_text("# Historical\n", encoding="utf-8")

    full = default_markdown_files(tmp_path)
    quick = default_markdown_files(tmp_path, include_archives=False)
    assert active in full and active in quick
    assert historical in full and historical not in quick
