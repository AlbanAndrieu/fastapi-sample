"""Static contract checks for the TrueNAS platform UI diagnostics."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSET = ROOT / "nabla" / "api" / "assets" / "api-truenas.js"


def test_truenas_platform_displays_public_wan_metadata() -> None:
    javascript = ASSET.read_text(encoding="utf-8")

    assert "diagnostics?.wan" in javascript
    assert "pfSense WAN / homelab public endpoint ${wan.ipv4}" in javascript
    assert "static IPv4" in javascript


def test_truenas_platform_displays_ingress_filter_observations() -> None:
    javascript = ASSET.read_text(encoding="utf-8")

    assert "security_filters" in javascript
    assert "Ingress filters" in javascript
    assert "truenas-security-filters" in javascript
    assert 'filter?.state === "blocked"' in javascript
    assert 'filter?.state === "in_path"' in javascript
    assert 'filter?.state === "running"' in javascript


def test_truenas_platform_displays_proven_snort_pf_block() -> None:
    javascript = ASSET.read_text(encoding="utf-8")

    assert "ingress_block" in javascript
    assert "truenas-ingress-block" in javascript
    assert "Ingress blocked by ${engine} → ${firewall}" in javascript
    assert "FastAPI Cloud egress" not in javascript  # role comes from sanitized API evidence
    assert 'ingressBlock?.state === "blocked"' in javascript
    assert "blocked by Snort/PF" in javascript
