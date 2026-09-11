"""HTML shell for the GET /api landing page."""

from __future__ import annotations

from html import escape

_PUBLIC_API_URL = "https://fastapi-sample.fastapicloud.dev/api"
_OPEN_GRAPH_IMAGE_URL = f"{_PUBLIC_API_URL}/assets/open-graph.png"
_PAGE_DESCRIPTION = "FastAPI sample application with health diagnostics, search integrations, MCP and homelab observability."


def render_api_root_page(
    *,
    title_suffix: str | None,
    app_version: str,
    runtime_mode: str | None = None,
    is_fastapi_cloud: bool = False,
) -> str:
    """Build the API landing page while CSS and behavior live in static assets."""
    title = escape(title_suffix or "fastapi-sample")
    description = escape(_PAGE_DESCRIPTION)
    mode = runtime_mode or ("fastapi_cloud" if is_fastapi_cloud else "local")
    profiles = {
        "fastapi_cloud": {
            "context": "FastAPI Cloud production",
            "title": "FastAPI Cloud runtime",
            "description": ("External production observer. Shared Redis heartbeats provide cross-replica evidence when available."),
            "instance_label": "Observed instances",
            "replica_label": "FastAPI Cloud replicas",
            "replica_value": "control-plane only",
            "note": ("Observed runtime heartbeats are not the authoritative FastAPI Cloud control-plane replica count."),
            "hero": "FastAPI Cloud",
            "badge": "status-badge--cloud",
        },
        "homelab": {
            "context": "TrueNAS homelab production",
            "title": "TrueNAS homelab runtime",
            "description": ("Trusted-LAN production observer for TrueNAS, pfSense and Prometheus health and platform telemetry."),
            "instance_label": "Observed instances",
            "replica_label": "Observer scope",
            "replica_value": "trusted LAN",
            "note": ("This production runtime observes private homelab dependencies from the trusted LAN without exposing them to a cloud observer."),
            "hero": "TrueNAS homelab",
            "badge": "status-badge--local",
        },
        "cloud_paas": {
            "context": "Cloud/PaaS production",
            "title": "Cloud/PaaS runtime",
            "description": "External cloud/PaaS runtime and outbound egress observation.",
            "instance_label": "Observed instances",
            "replica_label": "Runtime scope",
            "replica_value": "external",
            "note": "Observed application heartbeats are not provider control-plane capacity.",
            "hero": "cloud/PaaS",
            "badge": "status-badge--cloud",
        },
        "local": {
            "context": "Local workstation",
            "title": "Local workstation runtime",
            "description": ("Observed local runtime processes and outbound egress. Shared Redis heartbeats may include sibling workstation processes."),
            "instance_label": "Observed processes",
            "replica_label": "Runtime scope",
            "replica_value": "local process",
            "note": ("Local runtime heartbeats describe this workstation view; they are not a cloud control-plane replica count."),
            "hero": "local workstation",
            "badge": "status-badge--local",
        },
    }
    profile = profiles.get(mode, profiles["local"])
    runtime_context = profile["context"]
    runtime_title = profile["title"]
    runtime_description = profile["description"]
    instance_label = profile["instance_label"]
    replica_label = profile["replica_label"]
    replica_value = profile["replica_value"]
    runtime_note = profile["note"]
    hero_runtime = profile["hero"]
    badge_class = profile["badge"]
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>FastAPI Sample · {runtime_context} · {title}</title>
        <meta name="description" content="{description}">
        <link rel="canonical" href="{_PUBLIC_API_URL}">
        <meta property="og:type" content="website">
        <meta property="og:site_name" content="fastapi-sample">
        <meta property="og:title" content="FastAPI sample — {title}">
        <meta property="og:description" content="{description}">
        <meta property="og:url" content="{_PUBLIC_API_URL}">
        <meta property="og:image" content="{_OPEN_GRAPH_IMAGE_URL}">
        <meta property="og:image:width" content="1200">
        <meta property="og:image:height" content="630">
        <meta property="og:image:alt" content="FastAPI sample service overview">
        <meta name="twitter:card" content="summary_large_image">
        <meta name="twitter:title" content="FastAPI sample — {title}">
        <meta name="twitter:description" content="{description}">
        <meta name="twitter:image" content="{_OPEN_GRAPH_IMAGE_URL}">
        <link rel="icon" type="image/x-icon" href="/favicon.ico">
        <link rel="stylesheet" href="/api/assets/api.css?v={app_version}">
    </head>
    <body>
        <header>
            <nav>
                <a href="/" class="logo">FastAPI Sample · {title}</a>
                <div class="nav-links">
                    <a href="/docs">API Docs</a>
                    <a href="/api/data">API</a>
                    <a href="#health-board">Health</a>
                    <a href="/api/topology">Topology</a>
                </div>
            </nav>
        </header>
        <main>
            <div class="hero">
                <div class="status-badge {badge_class}">
                    <span class="status-dot" aria-hidden="true"></span>
                    <span>{runtime_context}</span>
                </div>
                <h1>FastAPI sample</h1>
                <p class="subtitle">Runtime-aware diagnostics for {hero_runtime}.</p>
                <div class="hero-code"><code>GET /api</code></div>
            </div>

            <section class="health-board" id="health-board" aria-labelledby="health-board-title">
                <div class="health-board-heading-row">
                    <div>
                        <h2 id="health-board-title">Service health</h2>
                        <p class="health-board-subtitle">Operational outcome, dependency risk, security posture and probe evidence from this runtime.</p>
                    </div>
                    <div class="service-filter">
                        <label for="service-filter">Filter services</label>
                        <div class="service-filter-control">
                            <input id="service-filter" type="search" autocomplete="off" placeholder="Search service, status, role…">
                            <button type="button" id="service-filter-clear">Clear</button>
                            <button type="button" id="service-expand-issues" aria-pressed="false">Issues</button>
                            <button type="button" id="service-collapse-all" aria-expanded="true">Collapse</button>
                        </div>
                    </div>
                </div>
                <div class="service-health-overview" id="service-health-overview" aria-live="polite"></div>
                <ul class="health-checks" id="health-checks"></ul>
                <div class="service-groups" id="health-services-groups"></div>
            </section>

            <section class="sickz-board" aria-labelledby="sickz-board-title">
                <div class="health-board-heading-row">
                    <div>
                        <h2 id="sickz-board-title">Exposure security posture</h2>
                        <p class="health-board-subtitle">Expected exposure policy and externally observed reachability remain separate from functional health.</p>
                    </div>
                </div>
                <ul class="health-checks" id="sickz-checks"></ul>
            </section>

            <section class="truenas-platform" id="truenas-platform" aria-labelledby="truenas-platform-title">
                <h2 id="truenas-platform-title">Core drill-down · TrueNAS platform + API</h2>
                <p class="health-board-subtitle">Authoritative storage-platform evidence and authenticated API diagnostics from the current observer.</p>
                <div id="truenas-pipeline"></div>
            </section>

            <section class="runtime-topology" id="runtime-topology" aria-labelledby="runtime-topology-title">
                <h2 id="runtime-topology-title">{runtime_title}</h2>
                <p class="health-board-subtitle">{runtime_description}</p>
                <div class="runtime-topology-grid">
                    <div>
                        <span>{instance_label}</span>
                        <strong id="runtime-instance-count">—</strong>
                    </div>
                    <div>
                        <span>{replica_label}</span>
                        <strong>{replica_value}</strong>
                    </div>
                </div>
                <p class="runtime-topology-note">{runtime_note}</p>
            </section>
        </main>
        <script type="module" src="/api/assets/api-health.js?v={app_version}"></script>
    </body>
    </html>
    """
