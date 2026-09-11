"""Dedicated homelab topology visualization page."""

from __future__ import annotations

from html import escape

_CYTOSCAPE_VERSION = "3.33.1"
_CYTOSCAPE_URL = (
    "https://cdnjs.cloudflare.com/ajax/libs/cytoscape/"
    f"{_CYTOSCAPE_VERSION}/cytoscape.min.js"
)
_CYTOSCAPE_INTEGRITY = (
    "sha512-kHAY8XzRfLVMcLuowdk91552RD+Nb2/1uHamfHMdLejNqlZnbEJLl1wYnsNnqIFCEZ++"
    "WaOcOlfokC6p9JWrLw=="
)


def render_topology_page(*, title_suffix: str | None, app_version: str) -> str:
    """Render a standalone Cytoscape.js topology screen without changing GET /api."""
    title = escape(title_suffix or "fastapi-sample")
    version = escape(app_version)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Homelab topology · {title}</title>
    <meta name="description" content="Interactive declared homelab service dependencies and network-flow relations.">
    <link rel="icon" type="image/x-icon" href="/favicon.ico">
    <link rel="stylesheet" href="/api/assets/api-base.css?v={version}">
    <link rel="stylesheet" href="/api/assets/api-topology.css?v={version}">
    <script defer src="{_CYTOSCAPE_URL}"
        integrity="{_CYTOSCAPE_INTEGRITY}"
        crossorigin="anonymous" referrerpolicy="no-referrer"></script>
    <script type="module" src="/api/assets/api-topology.js?v={version}"></script>
</head>
<body>
    <header>
        <nav>
            <a href="/api/topology" class="logo">FastAPI Sample · Topology</a>
            <div class="nav-links">
                <a href="/api">Health</a>
                <a href="/api/homelab-topology">Topology JSON</a>
                <a href="/docs">API Docs</a>
            </div>
        </nav>
    </header>
    <main class="topology-page">
        <section class="topology-heading" aria-labelledby="topology-title">
            <div>
                <p class="topology-kicker">Declared architecture · version {version}</p>
                <h1 id="topology-title">Homelab topology</h1>
                <p class="subtitle">Dependencies and network/service relations from the canonical <code>nabla-compose</code> topology contract. This view does not infer live health.</p>
            </div>
            <div class="topology-stats" aria-live="polite">
                <span><strong id="topology-node-count">—</strong> nodes</span>
                <span><strong id="topology-edge-count">—</strong> relations</span>
                <span><strong id="topology-visible-count">—</strong> visible</span>
            </div>
        </section>

        <section class="topology-toolbar" aria-label="Topology controls">
            <label>Search
                <input id="topology-search" type="search" autocomplete="off" placeholder="Service, kind, category…">
            </label>
            <label>Relation
                <select id="topology-relation-filter"><option value="all">All relations</option></select>
            </label>
            <label>Strength
                <select id="topology-strength-filter">
                    <option value="all">Required + optional</option>
                    <option value="required">Required</option>
                    <option value="optional">Optional</option>
                </select>
            </label>
            <label>Layout
                <select id="topology-layout">
                    <option value="cose">CoSE</option>
                    <option value="breadthfirst">Dependency layers</option>
                    <option value="concentric">Concentric</option>
                    <option value="grid">Grid</option>
                </select>
            </label>
            <div class="topology-actions">
                <button type="button" id="topology-fit">Fit</button>
                <button type="button" id="topology-reset">Reset</button>
            </div>
        </section>

        <p class="topology-status" id="topology-status">Loading declared topology…</p>
        <p class="topology-error" id="topology-error" hidden></p>

        <section class="topology-workspace">
            <div id="topology-graph" class="topology-graph" role="img" aria-label="Interactive homelab dependency graph"></div>
            <aside class="topology-details" aria-labelledby="topology-details-title">
                <h2 id="topology-details-title">Selection</h2>
                <p id="topology-details-empty">Select a node or relation to inspect its declared metadata and blast radius.</p>
                <dl id="topology-details-list" hidden></dl>
            </aside>
        </section>

        <section class="topology-legend" aria-label="Topology legend">
            <span><i class="topology-swatch topology-swatch--critical"></i>critical</span>
            <span><i class="topology-swatch topology-swatch--high"></i>high</span>
            <span><i class="topology-swatch topology-swatch--service"></i>service</span>
            <span><i class="topology-line"></i>required relation</span>
            <span><i class="topology-line topology-line--optional"></i>optional relation</span>
        </section>
    </main>
</body>
</html>"""
