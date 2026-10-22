"""Embed a validated Git commit SHA into the FastAPI Cloud source bundle."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

_TARGET = Path(__file__).resolve().parents[1] / "nabla" / "_deployment_revision.py"
_SHA = re.compile(r"[0-9a-f]{40}")


def stamp_revision(revision: str, *, target: Path = _TARGET) -> None:
    """Only the checkout's full immutable commit ID is accepted."""
    if not _SHA.fullmatch(revision):
        raise ValueError("expected a lowercase 40-character Git SHA")
    if not target.is_file():
        raise FileNotFoundError("tracked revision module is missing")
    target.write_text(
        '"""Artifact-embedded immutable Git commit SHA."""\n\n'
        f'DEPLOYED_BUILD_SHA = "{revision}"\n',
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("revision", help="Git checkout SHA")
    args = parser.parse_args()
    stamp_revision(args.revision)


if __name__ == "__main__":
    main()
