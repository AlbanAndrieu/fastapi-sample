"""Contracts for base-scoped destructive-diff acknowledgements."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "agent-quality-gate.sh"
ACK = ROOT / ".quality-gate-large-deletions"
ACK_RE = re.compile(r"^(?P<base>[0-9a-f]{40}) (?P<path>\S.*)$")


def test_large_deletion_ack_is_bound_to_exact_comparison_base() -> None:
    text = GATE.read_text(encoding="utf-8")

    assert "QUALITY_LARGE_DELETION_ACK_FILE" in text
    assert 'BASE_SHA="$(git rev-parse "${BASE_REF}^{commit}")"' in text
    assert 'git diff --quiet "${BASE_REF}" -- "${LARGE_DELETION_ACK_FILE}"' in text
    assert 'grep -Fxq -- "${BASE_SHA} ${file}" "${LARGE_DELETION_ACK_FILE}"' in text
    assert "QG_LARGE_DELETION_ACK" in text
    assert "QUALITY_ALLOW_LARGE_DELETION=1" in text


def test_ack_file_contains_only_base_scoped_entries() -> None:
    entries = [
        line.strip()
        for line in ACK.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    matches = [ACK_RE.fullmatch(entry) for entry in entries]
    assert all(match is not None for match in matches)
    assert len({match.group("path") for match in matches if match}) == len(entries)
