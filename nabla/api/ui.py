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
    is_fastapi_cloud: bool = False,
) -> str:
    """Build the API landing page while CSS and behavior live in static assets."""
    title = escape(title_suffix or "fastapi-sample")
    description = escape(_PAGE_DESCRIPTION)
    runtime_mode = "fastapi_cloud" if is_fastapi_cloud else "local"
    runtime_context = "FastAPI Cloud production" if is_fastapi_cloud else "Local workstation"
    runtime_title = "FastAPI Cloud runtime" if is_fastapi_cloud else "Local workstation runtime"
    runtime_description = (
        "Observed application runtimes and outbound egress. Shared Redis heartbeats provide cross-replica evidence when available."
        if is_fastapi_cloud
        else "Observed local runtime processes and outbound egress. Shared Redis heartbeats may include sibling workstation processes."
    )
    instance_label = "Observed instances" if is_fastapi_cloud else "Observed processes"
    replica_label = "FastAPI Cloud replicas" if is_fastapi_cloud else "Runtime scope"
    replica_value = "control-plane only" if is_fastapi_cloud else "local process"
    runtime_note = (
        "Observed runtime heartbeats are not the authoritative FastAPI Cloud control-plane replica count."
        if is_fastapi_cloud
        else "Local runtime heartbeats describe this workstation view; they are not a cloud control-plane replica count."
    )
    hero_runtime = "FastAPI Cloud" if is_fastapi_cloud else "local workstation"
    badge_class = "status-badge--cloud" if is_fastapi_cloud else "status-badge--local"
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
        <link rel="stylesheet" href="/api/assets/api.css">
    </head>
    <body>
        <header>
            <nav>
                <a href="/" class="logo">FastAPI Sample · {title}</a>
                <div class="nav-links">
                    <a href="/docs">API Docs</a>
                    <a href="/api/data">API</a>
                    <a href="#health-board">Health</a>
                </div>
            </nav>
        </header>
        <main>
            <div class="hero">
                <div class="status-badge {badge_class}">
                    <span class="status-dot" aria-hidden="true"></span>
                    <span>{runtime_context}</span>
                </div>
                <h1>{title}</h1>
                <p class="subtitle">FastAPI runtime · version <strong>{app_version}</strong></p>
                <div class="hero-code">
                    <pre><code><span class="keyword">from</span> <span class="module">fastapi</span> <span class="keyword">import</span> <span class="class">FastAPI</span>

<span class="variable">app</span> = <span class="class">FastAPI</span>()

<span class="decorator">@app.get</span>(<span class="string">"/"</span>)
<span class="keyword">def</span> <span class="function">read_root</span>():
    <span class="keyword">return</span> {{<span class="string">"runtime"</span>: <span class="string">"{hero_runtime}"</span>, <span class="string">"status"</span>: <span class="string">"ready"</span>}}</code></pre>
                </div>
            </div>

            <section class="health-board" id="health-board" aria-labelledby="health-board-title">
                <div class="health-board-heading-row">
                    <div>
                        <h2 class="health-board-title" id="health-board-title">Service health</h2>
                        <p class="health-board-meta">Live dependency and exposure observability, grouped by declared blast radius.</p>
                    </div>
                    <div class="service-filter">
                        <label for="service-filter">Filter services</label>
                        <div class="service-filter-control">
                            <input id="service-filter" type="search" autocomplete="off" placeholder="Name, host, tier or status">
                            <button type="button" id="service-filter-clear">Clear</button>
                            <button type="button" id="service-expand-issues">Issues</button>
                            <button type="button" id="service-collapse-all">Collapse</button>
                        </div>
                    </div>
                </div>
                <p class="health-board-meta">Live view of <a href="/healthz">/healthz</a>.
                    <button type="button" class="health-refresh">Refresh</button>
                </p>
                <div class="health-summary health-summary--neutral" id="health-summary">
                    <span class="health-led health-led--gray" id="health-summary-led" aria-hidden="true"></span>
                    <span id="health-summary-text">Loading health checks…</span>
                </div>

                <section class="runtime-topology" id="runtime-topology" data-runtime-mode="{runtime_mode}" aria-labelledby="runtime-topology-title">
                    <div class="runtime-topology-heading">
                        <div>
                            <h3 id="runtime-topology-title">{runtime_title}</h3>
                            <p class="health-board-meta">{runtime_description}</p>
                        </div>
                        <span class="runtime-topology-state runtime-topology-state--warn" id="runtime-topology-state">Loading…</span>
                    </div>
                    <div class="runtime-topology-grid">
                        <div class="runtime-topology-metric">
                            <span id="runtime-instance-label">{instance_label}</span>
                            <strong id="runtime-instance-count">—</strong>
                        </div>
                        <div class="runtime-topology-metric">
                            <span id="runtime-replica-label">{replica_label}</span>
                            <strong id="runtime-replica-count">{replica_value}</strong>
                        </div>
                        <div class="runtime-topology-metric">
                            <span>Aggregation</span>
                            <strong id="runtime-aggregation">—</strong>
                        </div>
                        <div class="runtime-topology-metric">
                            <span>Redis server memory</span>
                            <strong id="runtime-redis-memory">—</strong>
                        </div>
                        <div class="runtime-topology-metric">
                            <span>Redis DB keys</span>
                            <strong id="runtime-redis-keys">—</strong>
                        </div>
                        <div class="runtime-topology-metric">
                            <span>Redis clients</span>
                            <strong id="runtime-redis-clients">—</strong>
                        </div>
                        <div class="runtime-topology-metric">
                            <span>Redis ops / sec</span>
                            <strong id="runtime-redis-ops">—</strong>
                        </div>
                        <div class="runtime-topology-metric">
                            <span>Redis hit rate</span>
                            <strong id="runtime-redis-hit-rate">—</strong>
                        </div>
                        <div class="runtime-topology-metric">
                            <span>Redis evictions</span>
                            <strong id="runtime-redis-evictions">—</strong>
                        </div>
                    </div>
                    <p class="runtime-topology-note" id="runtime-redis-scope">Application Redis backend · provider attribution pending telemetry.</p>
                    <div class="runtime-topology-egress">
                        <span class="runtime-topology-label">Active egress IPs</span>
                        <div class="runtime-topology-pills" id="runtime-active-egress">Loading…</div>
                    </div>
                    <div class="runtime-topology-egress">
                        <span class="runtime-topology-label">Recent egress IPs · 24 h</span>
                        <div class="runtime-topology-pills" id="runtime-recent-egress">Loading…</div>
                    </div>
                    <div class="runtime-instance-list" id="runtime-instance-list" aria-live="polite"></div>
                    <p class="runtime-topology-note" id="runtime-count-semantics">{runtime_note}</p>
                </section>

                <div class="service-group-heading service-group-heading--core" id="health-core-group-heading">
                    <div>
                        <h3>Core services</h3>
                        <p>Required for core stack</p>
                    </div>
                </div>
                <ul class="health-checks" id="health-checks"></ul>
                <p class="health-error" id="health-fetch-error" hidden></p>

                <section class="truenas-platform" id="truenas-platform" data-service-filter-target data-search-text="truenas storage platform required infrastructure https websocket api" aria-labelledby="truenas-platform-title">
                    <div class="truenas-platform-heading">
                        <div>
                            <h3 class="health-subboard-title truenas-platform-title" id="truenas-platform-title">TrueNAS platform</h3>
                            <p class="health-board-meta">Required infrastructure dependency · HTTPS and WebSocket API diagnostics.</p>
                        </div>
                        <span class="truenas-platform-state truenas-platform-state--neutral" id="truenas-platform-state">Loading…</span>
                    </div>
                    <div class="truenas-platform-target" id="truenas-platform-target">https://truenas.albandrieu.com:7000</div>
                    <div class="truenas-pipeline" id="truenas-pipeline" aria-live="polite"></div>
                    <p class="health-error" id="truenas-platform-error" hidden></p>
                </section>

                <div class="service-groups" id="health-services-groups" aria-live="polite"></div>

                <h3 class="health-subboard-title" id="sickz-board-title">Exposure security policy</h3>
                <p class="health-board-meta">Live view of <a href="/sickz">/sickz</a>.
                    <button type="button" class="health-refresh">Refresh</button>
                </p>
                <p class="health-board-meta"><code>/sickz</code> compares declared exposure intent with
                    external HTTP/TLS and read-only Cloudflare Tunnel evidence. Services with
                    <code>external=false</code> must stay unreachable from outside the home LAN. Services with
                    <code>external=true</code> must be reachable; when <code>tunnelSecure=true</code>, Cloudflare
                    protection is expected and verified. Direct <code>*.int.albandrieu.com</code> exposure is an
                    explicit weaker-security exception only with <code>tunnelSecure=false</code> and is shown as
                    an orange warning. Probes are skipped on the internal network unless a cloud/PaaS runtime is
                    detected. TLS trust is checked separately so certificate failures remain visible.</p>
                <div class="health-summary health-summary--neutral" id="sickz-summary">
                    <span class="health-led health-led--gray" id="sickz-summary-led" aria-hidden="true"></span>
                    <span id="sickz-summary-text">Loading sickz checks…</span>
                </div>
                <p class="health-board-meta" id="sickz-lan-hint" hidden style="margin-top: 0.35rem"></p>
                <div id="sickz-pfsense-wrap" class="sickz-pfsense-wrap" hidden></div>
                <ul class="health-checks" id="sickz-checks"></ul>
                <p class="health-error" id="sickz-fetch-error" hidden></p>
            </section>

            <div class="cards">
                <div class="card">
                    <h3>Interactive API Docs</h3>
                    <p>Explore this API's endpoints with the interactive Swagger UI. Test requests and view response schemas in real-time.</p>
                    <a href="/docs">Open Swagger UI →</a>
                </div>
                <div class="card">
                    <h3>Sample Data</h3>
                    <p>Access sample JSON data through our REST API. Perfect for testing and development purposes.</p>
                    <a href="/api/data">Get Data →</a>
                </div>
            </div>
        </main>
        <script type="module" src="/api/assets/api-health.js"></script>
    </body>
    </html>
    """
