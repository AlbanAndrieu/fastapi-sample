"""Validate repository-local Markdown links without network access."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
LINK_RE = re.compile(
    r"""!?\[[^\]]*\]\(
        (?P<target><[^>]+>|[^)\s]+)
        (?:\s+(?:"[^"]*"|'[^']*'))?
    \)""",
    re.VERBOSE,
)


def resolve_local_target(source: Path, raw_target: str, root: Path) -> Path | None:
    """Resolve one local Markdown target or return None for non-file links."""

    target = raw_target.strip("<>")
    if not target or target.startswith("#"):
        return None

    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or target.startswith("//"):
        return None

    path_part = unquote(parsed.path)
    if not path_part:
        return None

    if path_part.startswith("/"):
        candidate = root.resolve() / path_part.lstrip("/")
    else:
        candidate = source.parent / path_part
    return candidate.resolve()


def validate_markdown(source: Path, root: Path = ROOT) -> list[str]:
    """Return deterministic validation errors for one Markdown file."""

    errors: list[str] = []
    source = source.resolve()
    root = root.resolve()

    if not source.is_file():
        return [f"{source}: Markdown source does not exist"]

    for line_number, line in enumerate(
        source.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        for match in LINK_RE.finditer(line):
            raw_target = match.group("target")
            target = resolve_local_target(source, raw_target, root)
            if target is None:
                continue
            try:
                relative_target = target.relative_to(root)
            except ValueError:
                errors.append(
                    f"{source.relative_to(root)}:{line_number}: "
                    f"link escapes repository: {raw_target}",
                )
                continue
            if not target.exists():
                errors.append(
                    f"{source.relative_to(root)}:{line_number}: "
                    f"missing local target: {relative_target}",
                )

    return errors


def default_markdown_files(root: Path = ROOT) -> list[Path]:
    """Return canonical Markdown documentation files for a full manual check."""

    files = [root / "README.md", root / "AGENTS.md"]
    files.extend(sorted((root / "docs").rglob("*.md")))
    return [path for path in files if path.is_file()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args()

    sources = [
        path if path.is_absolute() else ROOT / path
        for path in args.paths
    ] or default_markdown_files()

    errors = [
        error
        for source in sources
        for error in validate_markdown(source)
    ]
    if errors:
        print("\n".join(errors))
        return 1

    print(f"Documentation link contract passed for {len(sources)} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
