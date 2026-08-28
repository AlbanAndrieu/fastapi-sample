"""HTML shell for the GET /api landing page."""

from __future__ import annotations

from html import escape

_PUBLIC_API_URL = "https://fastapi-sample.fastapicloud.dev/api"
_OPEN_GRAPH_IMAGE_URL = f"{_PUBLIC_API_URL}/assets/open-graph.png"
_PAGE_DESCRIPTION = "FastAPI sample application with health diagnostics, search integrations, MCP and homelab observability."


def render_api_root_page(*, title_suffix: str | None, app_version: str) -> str:
    """Build the API landing page while CSS and behavior live in static assets."""
    title = escape(title_suffix or "fastapi-sample")
    description = escape(_PAGE_DESCRIPTION)
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Vercel + FastAPI : {title} </title>
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
                <a href="/" class="logo">Vercel + FastAPI : {title}</a>
                <div class="nav-links">
                    <a href="/docs">API Docs</a>
                    <a href="/api/data">API</a>
                    <a href="#health-board">Health</a>
                </div>
            </nav>
        </header>
        <main>
            <div class="hero">
                <h1>Vercel + FastAPI : {title}</h1>
                <p class="subtitle" style="margin-top: -0.5rem;">App version : <strong>{app_version}</strong></p>
                <div class="hero-code">
                    <pre><code><span class="keyword">from</span> <span class="module">fastapi</span> <span class="keyword">import</span> <span class="class">FastAPI</span>

<span class="variable">app</span> = <span class="class">FastAPI</span>()

<span class="decorator">@app.get</span>(<span class="string">"/"</span>)
<span class="keyword">def</span> <span class="function">read_root</span>():
    <span class="keyword">return</span> {{<span class="string">"Python"</span>: <span class="string">"on Vercel"</span>}}</code></pre>
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
