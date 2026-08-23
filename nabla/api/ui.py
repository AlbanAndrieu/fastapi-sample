"""HTML shell for the GET /api landing page."""

from __future__ import annotations


def render_api_root_page(*, title_suffix: str | None, app_version: str) -> str:
    """Build the API landing page while CSS and behavior live in static assets."""
    title = str(title_suffix)
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Vercel + FastAPI : {title} </title>
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
                <h2 class="health-board-title" id="health-board-title">Service health</h2>
                <p class="health-board-meta">Live view of <a href="/healthz">/healthz</a>.
                    <button type="button" class="health-refresh">Refresh</button>
                </p>
                <div class="health-summary health-summary--neutral" id="health-summary">
                    <span class="health-led health-led--gray" id="health-summary-led" aria-hidden="true"></span>
                    <span id="health-summary-text">Loading health checks…</span>
                </div>
                <ul class="health-checks" id="health-checks"></ul>
                <p class="health-error" id="health-fetch-error" hidden></p>

                <h3 class="health-subboard-title" id="sickz-board-title">Unreachable targets</h3>
                <p class="health-board-meta">Live view of <a href="/sickz">/sickz</a>.
                    <button type="button" class="health-refresh">Refresh</button>
                </p>
                <p class="health-board-meta">These URLs must <strong>not</strong> respond when this app runs
                    outside your home LAN. Probes are skipped when <code>SICKZ_INTERNAL_NETWORK=true</code>, or
                    implicitly when <code>SICKZ_NETWORK_LABEL=nabla</code> or
                    <code>APP_DOMAIN=albandrieu.albandrieu.com</code> (unless a cloud/PaaS runtime is detected).
                    <code>SICKZ_NETWORK_LABEL</code> / <code>APP_DOMAIN</code> also name the network in messages.
                    Separate equivalent URLs with <code>|</code>; separate unrelated targets with commas.
                    Probes use TLS verify off so certificate issues do not hide reachability.</p>
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
        <script src="/api/assets/api-health.js" defer></script>
    </body>
    </html>
    """
