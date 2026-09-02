"""UI contracts for pfSense liveness and ingress security telemetry."""

from pathlib import Path


_ASSET_DIR = Path(__file__).parents[2] / "nabla" / "api" / "assets"


def test_direct_probe_url_is_a_health_link_and_tls_target() -> None:
    script = (_ASSET_DIR / "api-health-ui.js").read_text(encoding="utf-8")
    href_start = script.index("export function tunnelHref")
    href_end = script.index("export function httpStatusIsSuccess2xx", href_start)
    href = script[href_start:href_end]

    assert "check.url" in href
    assert 'pfsense: "pfsense.svg"' in script


def test_ingress_pipeline_has_visible_clear_snort_state() -> None:
    script = (_ASSET_DIR / "api-truenas.js").read_text(encoding="utf-8")

    assert 'filter?.state === "running" || filter?.state === "clear"' in script
    assert 'filter?.state === "in_path" || filter?.state === "observed"' in script
