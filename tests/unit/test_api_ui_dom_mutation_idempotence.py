"""Regression: /api must not continuously mutate its own observed DOM."""

from pathlib import Path

ASSETS = Path(__file__).resolve().parents[2] / "nabla" / "api" / "assets"


def source(name: str) -> str:
    return (ASSETS / name).read_text(encoding="utf-8")


def test_probe_order_does_not_reappend_every_badge_on_each_animation_frame():
    followup = source("api-health-ui-final-followup.js")
    sorter = source("api-probe-stable-order.js")
    assert "reorderProbeNodesIfNeeded(strip, probes, order)" in followup
    assert "strip.appendChild(probe)" not in followup
    assert "desired.every((probe, index) => probe === probes[index])" in sorter
    assert "return false;" in sorter
    assert "strip.appendChild(probe)" in sorter


def test_final_ui_decoration_avoids_redundant_observed_writes():
    followup = source("api-health-ui-final-followup.js")
    assert 'if (age.textContent !== value) age.textContent = value;' in followup
    assert 'if (!node.classList.contains("health-overflow-safe"))' in followup
    assert 'latency.classList.contains("health-meta-badge--probe-latency-unavailable")' in followup
    assert "new MutationObserver(schedule).observe(board" in followup


def test_polish_never_rewrites_same_tier_on_each_observer_run():
    polish = source("api-health-ui-polish.js")
    assert "note.textContent !== REQUIRED_TIER" in polish
    assert 'if (!note.classList.contains("health-tier-inline"))' in polish


def test_new_regression_test_demonstrates_zero_mutations_after_stabilization():
    script = (ASSETS.parents[2] / "tests/js/api-probe-stable-order.test.mjs").read_text(
        encoding="utf-8"
    )
    assert "afterFirstPass" in script
    assert "for (let i = 0; i < 100; i += 1)" in script
    assert "assert.equal(item.mutations, afterFirstPass)" in script


def test_filter_widget_updates_html_only_for_changed_render_signature():
    filter_js = source("api-global-service-filter.js")
    pure_gate = source("api-dom-render-signature.js")
    assert "shouldUpdateRenderSignature(button, signature)" in filter_js
    assert "if (!shouldUpdateRenderSignature(active, signature)) return;" in filter_js
    assert "active.replaceChildren()" in filter_js
    assert "if (element.dataset.renderSignature === signature) return false;" in pure_gate


def test_filter_and_probe_dom_guards_are_covered_by_node_regressions():
    js_tests = ASSETS.parents[2] / "tests/js"
    filter_regression = (js_tests / "api-filter-render-signature.test.mjs").read_text()
    probe_regression = (js_tests / "api-probe-stable-order.test.mjs").read_text()
    assert "for (let index = 0; index < 100; index += 1)" in filter_regression
    assert "for (let i = 0; i < 100; i += 1)" in probe_regression
