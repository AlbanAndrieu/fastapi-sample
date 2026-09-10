"""Contracts for reviewed per-path destructive-diff acknowledgements."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "agent-quality-gate.sh"
ACK = ROOT / ".quality-gate-large-deletions"


def test_large_deletion_ack_is_scoped_and_review_visible() -> None:
    text = GATE.read_text(encoding="utf-8")

    assert "QUALITY_LARGE_DELETION_ACK_FILE" in text
    assert "large_deletion_ack_file_changed" in text
    assert 'git diff --quiet "${BASE_REF}...HEAD" -- "${LARGE_DELETION_ACK_FILE}"' in text
    assert 'grep -Fxq -- "${file}" "${LARGE_DELETION_ACK_FILE}"' in text
    assert "QG_LARGE_DELETION_ACK" in text
    assert "QUALITY_ALLOW_LARGE_DELETION=1" in text


def test_current_refactor_acknowledges_only_reviewed_extractions() -> None:
    paths = {line.strip() for line in ACK.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")}

    assert paths == {
        "nabla/api/homelab_health_evidence.py",
        "nabla/api/platform_health.py",
    }
