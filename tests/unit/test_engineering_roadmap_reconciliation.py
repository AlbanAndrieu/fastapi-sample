"""FastAPI roadmap only tracks unreconciled acceptance, not completed code work."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_active_roadmap_has_one_owner_per_operational_layer() -> None:
    text = (ROOT / "docs/engineering-roadmap.md").read_text(encoding="utf-8")
    assert "Réconciliation mise à jour le 14 novembre 2026" in text
    assert "docs/roadmap-portfolio.md" in text
    assert "## P0" in text and "## P1" in text and "## P2" in text
    for item in ("F01", "F02", "F03", "F04", "F05", "F06", "F07", "F08", "F09", "F10", "F11", "F12"):
        assert item in text
    for marker in ("NOT_VERIFIED", "issues/355", "deux runs master", "RoutePolicy", "engineering-backlog.md", "archive/2026-10-29/engineering-roadmap-before-consolidation.md"):
        assert marker in text
    assert "Cloudflare Tunnel et secrets" in text
    assert "Compose pour les exporters et cibles, FastAPI pour la projection" in text
    assert "Compose pour DNS/Tunnel/Access" in text
    assert "H02/G1 → H01 → H05" in text
    assert "H17" in text and "F11" in text


def test_archived_snapshot_is_pinned_to_previous_commit() -> None:
    archive = (ROOT / "docs/archive/2026-11-13-roadmap-reconciliation.md").read_text(encoding="utf-8")
    assert "dd44c23c9ad365d06ef60b6b326633769b3f2311" in archive
    assert "aucune procédure à relancer" in archive
    assert "E01, E07" in archive and "E14" in archive
