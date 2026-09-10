#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


# 1. Converge the exact canonical pre-commit configuration already produced by
# the repository formatter in the sibling recovery branch. This keeps the gate
# strict instead of bypassing or weakening it.
subprocess.run(
    ["git", "fetch", "origin", "47aa2b29d7ff9a7742f7a6b309e32fc948ae8377", "--depth=1"],
    cwd=ROOT,
    check=True,
)
canonical_precommit = subprocess.check_output(
    ["git", "show", "47aa2b29d7ff9a7742f7a6b309e32fc948ae8377:.pre-commit-config.yaml"],
    cwd=ROOT,
    text=True,
)
write(".pre-commit-config.yaml", canonical_precommit)


# 2. Decouple high-frequency service refresh from expensive/visually noisy
# technical drill-downs. Technical views are populated once, then refreshed on
# demand when the operator expands them.
path = "nabla/api/assets/api-health.js"
text = read(path)
text = replace_once(
    text,
    "function loadHealthBoards({ forceRefresh = false, showPending = true } = {}) {\n  resetHealthBoardRequest({ forceRefresh });\n  if (showPending) markHealthBoardsPending();\n  loadRuntimeTopology();\n  loadTrueNas();\n  loadHealth();\n  loadSickz();",
    "function loadHealthBoards({\n  forceRefresh = false,\n  showPending = true,\n  includeTechnical = false,\n} = {}) {\n  resetHealthBoardRequest({ forceRefresh });\n  if (showPending) markHealthBoardsPending();\n  loadHealth();\n  loadSickz();\n  if (includeTechnical) {\n    loadRuntimeTopology();\n    loadTrueNas();\n  }",
    label="api-health loadHealthBoards",
)
text = replace_once(
    text,
    "function installAutomaticRefresh() {\n  scheduleAutomaticRefresh();\n  document.addEventListener(\"visibilitychange\", () => {\n    if (document.hidden || automaticRefreshInFlight) return;\n    scheduleAutomaticRefresh(0);\n  });\n}\n",
    "function technicalDetailsOpen() {\n  return (\n    document.getElementById(\"runtime-topology\")?.open === true ||\n    document.getElementById(\"truenas-probe-dashboard\")?.open === true\n  );\n}\n\nfunction installTechnicalDetailRefresh() {\n  const runtime = document.getElementById(\"runtime-topology\");\n  runtime?.addEventListener(\"toggle\", () => {\n    if (runtime.open) loadRuntimeTopology();\n  });\n\n  const fanout = document.getElementById(\"truenas-probe-dashboard\");\n  fanout?.addEventListener(\"toggle\", () => {\n    if (fanout.open) loadTrueNas();\n  });\n}\n\nfunction installAutomaticRefresh() {\n  scheduleAutomaticRefresh();\n  document.addEventListener(\"visibilitychange\", () => {\n    if (document.hidden || automaticRefreshInFlight) return;\n    scheduleAutomaticRefresh(0);\n  });\n}\n",
    label="api-health technical toggle helper",
)
text = replace_once(
    text,
    "    loadHealthBoards({ forceRefresh: true });",
    "    loadHealthBoards({\n      forceRefresh: true,\n      includeTechnical: technicalDetailsOpen(),\n    });",
    label="api-health manual refresh",
)
text = replace_once(
    text,
    "installProbeFanoutDashboard();\nstartProbeAgeTicker();\nloadHealthBoards();\ninstallAutomaticRefresh();",
    "installProbeFanoutDashboard();\ninstallTechnicalDetailRefresh();\nstartProbeAgeTicker();\nloadHealthBoards({ includeTechnical: true });\ninstallAutomaticRefresh();",
    label="api-health bootstrap",
)
write(path, text)


# 3. Keep the runtime panel collapsed by default and put the service board before
# technical drill-downs, because service outcomes are the operator's primary UI.
path = "nabla/api/ui.py"
text = read(path)
text = replace_once(
    text,
    '<details class="runtime-topology" id="runtime-topology" open data-runtime-mode="{mode}" aria-labelledby="runtime-topology-title">',
    '<details class="runtime-topology" id="runtime-topology" data-runtime-mode="{mode}" aria-labelledby="runtime-topology-title">',
    label="runtime default collapsed",
)
tech_start = text.index('            <section class="truenas-platform"')
health_start = text.index('            <section class="health-board"', tech_start)
cards_start = text.index('            <div class="cards">', health_start)
technical = text[tech_start:health_start]
health = text[health_start:cards_start]
text = text[:tech_start] + health + "\n" + technical + text[cards_start:]
write(path, text)


# 4. Convert the fan-out dashboard into a closed <details>. While closed, only
# update the compact summary line; do not rebuild the large body on every probe
# event. Opening it renders the latest retained payload immediately.
path = "nabla/api/assets/api-probe-fanout-dashboard.js"
text = read(path)
text = replace_once(
    text,
    '  root = document.createElement("section");',
    '  root = document.createElement("details");',
    label="fanout details element",
)
old_heading = '''  root.innerHTML = `
    <div class="probe-dashboard-heading">
      <div>
        <h4>Homelab probe fan-out</h4>
        <p id="probe-dashboard-activity">Waiting for the first bounded probe snapshot…</p>
      </div>
      <button type="button" id="probe-dashboard-refresh" class="probe-dashboard-refresh">Refresh view</button>
    </div>
    <div class="probe-dashboard-progress" aria-live="polite">'''
new_heading = '''  root.innerHTML = `
    <summary class="probe-dashboard-heading">
      <div>
        <h4>Homelab probe fan-out</h4>
        <p id="probe-dashboard-activity">Waiting for the first bounded probe snapshot…</p>
      </div>
      <span class="probe-dashboard-collapsed-hint">Details</span>
    </summary>
    <div class="probe-dashboard-body">
      <div class="probe-dashboard-actions">
        <button type="button" id="probe-dashboard-refresh" class="probe-dashboard-refresh">Refresh details</button>
      </div>
    <div class="probe-dashboard-progress" aria-live="polite">'''
text = replace_once(text, old_heading, new_heading, label="fanout heading")
old_tail = '''    <p class="probe-dashboard-note">Coverage counts eligible probe slots, not catalog services: one service may have both a public and LAN probe. Disabled or unconfigured targets are excluded from the eligible denominator. The server keeps the 12-per-scope bounded scheduler and 30-second snapshot cache.</p>
  `;'''
new_tail = '''    <p class="probe-dashboard-note">Coverage counts eligible probe slots, not catalog services: one service may have both a public and LAN probe. Disabled or unconfigured targets are excluded from the eligible denominator. The server keeps the 12-per-scope bounded scheduler and 30-second snapshot cache.</p>
    </div>
  `;'''
text = replace_once(text, old_tail, new_tail, label="fanout body tail")
text = replace_once(
    text,
    '''  const button = root.querySelector("#probe-dashboard-refresh");''',
    '''  root.addEventListener("toggle", () => {
    if (root.open && lastPayload) renderDashboard(lastPayload);
  });

  const button = root.querySelector("#probe-dashboard-refresh");''',
    label="fanout lazy toggle",
)
text = replace_once(
    text,
    '''function renderDashboard(data) {
  if (!ensureDashboard()) return;
  lastPayload = data;
  const model = progressModel(data);''',
    '''function renderDashboard(data) {
  const root = ensureDashboard();
  if (!root) return;
  lastPayload = data;
  const model = progressModel(data);
  renderActivity(
    `${model.coverage.toFixed(1)}% evidence · ${model.healthyCoverage.toFixed(1)}% healthy · ${model.counts.fail} failed · ${model.counts.warn} warning`,
  );
  if (!root.open) {
    clarifyRuntimeTimeout(data);
    return;
  }''',
    label="fanout closed rendering",
)
text = replace_once(
    text,
    '      button.textContent = "Refresh view";',
    '      button.textContent = "Refresh details";',
    label="fanout refresh label",
)
write(path, text)


# Style <details> summary/body without introducing animation that would itself
# make periodic updates visually distracting.
path = "nabla/api/assets/api-probe-fanout-dashboard.css"
text = read(path)
insert_after = '''.probe-dashboard {
  margin-top: 0.85rem;
  padding: 0.8rem;
  border: 1px solid #2d2d2d;
  border-radius: 10px;
  background: #0d0d0d;
}
'''
addition = '''
.probe-dashboard > summary {
  cursor: pointer;
  list-style: none;
}

.probe-dashboard > summary::-webkit-details-marker {
  display: none;
}

.probe-dashboard-collapsed-hint {
  flex-shrink: 0;
  color: #8f8f8f;
  font-size: 0.66rem;
}

.probe-dashboard[open] .probe-dashboard-collapsed-hint {
  color: #d7d7d7;
}

.probe-dashboard-body {
  margin-top: 0.65rem;
}

.probe-dashboard-actions {
  display: flex;
  justify-content: flex-end;
}
'''
text = replace_once(text, insert_after, insert_after + addition, label="fanout details css")
write(path, text)


# 5. Advisory pfSense/Snort telemetry is collapsed. A confirmed ingress block
# remains expanded because it changes the platform verdict and is actionable.
path = "nabla/api/assets/api-truenas.js"
text = read(path)
text = replace_once(
    text,
    '  container = document.createElement("div");',
    '  container = document.createElement("details");',
    label="pfsense details element",
)
text = replace_once(
    text,
    '''  const block = data?.pfsense?.dns?.ingress_block;
  const controlPath = block?.control_path;''',
    '''  const block = data?.pfsense?.dns?.ingress_block;
  const controlPath = block?.control_path;
  const wasOpen = container.open === true;''',
    label="pfsense preserve open",
)
text = text.replace(
    '''    container.hidden = true;
    container.innerHTML = "";
    container.className = "truenas-ingress-block";''',
    '''    container.hidden = true;
    container.open = false;
    container.innerHTML = "";
    container.className = "truenas-ingress-block";''',
)
text = replace_once(
    text,
    '''    container.hidden = false;
    container.innerHTML =
      "<strong>⚠ pfSense security telemetry temporarily unavailable</strong>" +
      `<span>${evidence}</span>` +
      (timing ? `<span>${timing}</span>` : "") +
      `<span>Control path: ${path} · ${escapeText(independence)}</span>`;''',
    '''    container.hidden = false;
    container.open = wasOpen;
    container.innerHTML =
      "<summary><strong>⚠ pfSense security telemetry temporarily unavailable</strong></summary>" +
      '<div class="truenas-ingress-detail">' +
      `<span>${evidence}</span>` +
      (timing ? `<span>${timing}</span>` : "") +
      `<span>Control path: ${path} · ${escapeText(independence)}</span>` +
      "</div>";''',
    label="pfsense unavailable collapsed",
)
text = replace_once(
    text,
    '''    container.hidden = false;
    container.innerHTML =
      "<strong>⚠ Snort telemetry stale · last-known-good table retained</strong>" +
      `<span>${evidence}</span>` +
      (timing ? `<span>${timing}</span>` : "") +
      `<span>${escapeText(match)}</span>`;''',
    '''    container.hidden = false;
    container.open = wasOpen;
    container.innerHTML =
      "<summary><strong>⚠ Snort telemetry stale · last-known-good table retained</strong></summary>" +
      '<div class="truenas-ingress-detail">' +
      `<span>${evidence}</span>` +
      (timing ? `<span>${timing}</span>` : "") +
      `<span>${escapeText(match)}</span>` +
      "</div>";''',
    label="pfsense stale collapsed",
)
text = replace_once(
    text,
    '''    container.hidden = false;
    container.innerHTML =
      "<strong>⚠ Snort telemetry available · egress attribution unavailable</strong>" +
      `<span>${escapeText(block?.evidence || "Runtime public egress IP was not observed")}</span>`;''',
    '''    container.hidden = false;
    container.open = wasOpen;
    container.innerHTML =
      "<summary><strong>⚠ Snort telemetry available · egress attribution unavailable</strong></summary>" +
      '<div class="truenas-ingress-detail">' +
      `<span>${escapeText(block?.evidence || "Runtime public egress IP was not observed")}</span>` +
      "</div>";''',
    label="pfsense attribution collapsed",
)
text = replace_once(
    text,
    '''  container.className = "truenas-ingress-block";
  container.hidden = false;
  container.innerHTML =
    `<strong>💀 Ingress blocked by ${engine} → ${firewall}</strong>` +
    `<span>${source} → ${destination}</span>` +
    `<span>Evidence: ${mechanism} · ${evidence}</span>`;''',
    '''  container.className = "truenas-ingress-block";
  container.hidden = false;
  container.open = true;
  container.innerHTML =
    `<summary><strong>💀 Ingress blocked by ${engine} → ${firewall}</strong></summary>` +
    '<div class="truenas-ingress-detail">' +
    `<span>${source} → ${destination}</span>` +
    `<span>Evidence: ${mechanism} · ${evidence}</span>` +
    "</div>";''',
    label="pfsense blocked expanded",
)
write(path, text)


# 6. Skip destructive service-list rebuilds when semantically relevant service
# state has not changed. Freshness text still updates independently.
path = "nabla/api/assets/api-health-core.js"
text = read(path)
text = replace_once(
    text,
    'import { organizeHealthRows } from "./api-service-groups.js";\n',
    'import { organizeHealthRows } from "./api-service-groups.js";\n\nlet lastHealthRowsSignature = null;\n',
    label="health signature variable",
)
sig_fn = '''
function healthRowsSignature(checks) {
  return JSON.stringify(
    Object.keys(checks)
      .sort()
      .map((key) => {
        const check = checks[key] || {};
        return [
          key,
          check.name,
          check.display_label,
          check.service_id,
          check.reachable,
          check.local_state,
          check.dependency_state,
          check.effective_state,
          check.http_status,
          check.skipped,
          check.warning,
          check.error_kind,
          check.stage,
          check.error,
          check.path,
          check.host,
          check.port,
          check.url,
          check.tls_trusted,
          check.dependency_detail,
        ];
      }),
  );
}
'''
text = replace_once(
    text,
    '\nfunction render(data, platformMetrics = null) {',
    sig_fn + '\nfunction render(data, platformMetrics = null) {',
    label="health signature function",
)
text = replace_once(
    text,
    '''  const checks = data.checks || {};
  const keys = sortKeys(Object.keys(checks)).filter(''',
    '''  const checks = data.checks || {};
  const signature = healthRowsSignature(checks);
  if (signature === lastHealthRowsSignature) return;
  lastHealthRowsSignature = signature;
  const keys = sortKeys(Object.keys(checks)).filter(''',
    label="health stable render guard",
)
text = replace_once(
    text,
    '''function showFetchError(message) {
  const summaryEl''',
    '''function showFetchError(message) {
  lastHealthRowsSignature = null;
  const summaryEl''',
    label="health error resets signature",
)
write(path, text)


# Do the same for exposure rows so Cloudflare/pfSense evidence does not flash
# when the policy outcome is unchanged.
path = "nabla/api/assets/api-sickz.js"
text = read(path)
text = replace_once(
    text,
    'import {\n  hasReachableNon2xxHttp,',
    'let lastSickzRowsSignature = null;\n\nimport {\n  hasReachableNon2xxHttp,',
    label="sickz signature variable",
)
sickz_sig = '''
function sickzRowsSignature(checks) {
  return JSON.stringify(
    Object.keys(checks)
      .sort()
      .map((key) => {
        const check = checks[key] || {};
        const aliases = Object.entries(check.alias_results || {})
          .sort(([left], [right]) => left.localeCompare(right))
          .map(([url, value]) => [
            url,
            value?.reachable,
            value?.http_status,
            value?.error_kind,
            value?.error,
          ]);
        return [
          key,
          check.name,
          check.display_label,
          check.policy_status,
          check.policy_detail,
          check.reachable,
          check.http_status,
          check.skipped,
          check.reason,
          check.error_kind,
          check.error,
          check.external,
          check.tunnel_secure,
          check.cloudflare_tunnel_observed,
          check.cloudflare_default_deny,
          check.cloudflare_service_auth_attempted,
          check.cloudflare_service_token_access_passed,
          check.cloudflare_access_policy_count,
          check.tls_trusted,
          aliases,
        ];
      }),
  );
}
'''
text = replace_once(
    text,
    '\nfunction render(data) {',
    sickz_sig + '\nfunction render(data) {',
    label="sickz signature function",
)
text = replace_once(
    text,
    '''  const checks = data.checks || {};
  const pfKey = renderPfsenseSection(checks, classifySick, detailSickText);''',
    '''  const checks = data.checks || {};
  const signature = sickzRowsSignature(checks);
  if (signature === lastSickzRowsSignature) return;
  lastSickzRowsSignature = signature;
  const pfKey = renderPfsenseSection(checks, classifySick, detailSickText);''',
    label="sickz stable render guard",
)
text = replace_once(
    text,
    '''function showFetchError(message) {
  const summaryEl''',
    '''function showFetchError(message) {
  lastSickzRowsSignature = null;
  const summaryEl''',
    label="sickz error resets signature",
)
write(path, text)


# 7. ZAP Web + API DAST. Both scan the exact PR source by starting a local,
# ephemeral FastAPI runtime. The API scan is intentionally never pointed at
# production because it performs active attacks from the OpenAPI contract.
write(
    ".zap/web-rules.tsv",
    """10020\tFAIL\t(Anti-clickjacking header must be present and valid)\n10021\tFAIL\t(X-Content-Type-Options must be nosniff)\n10033\tFAIL\t(Directory browsing must not be exposed)\n10015\tWARN\t(Cache-control findings are visible but not blocking on the local HTTP DAST target)\n10023\tWARN\t(Debug error disclosure requires triage)\n10035\tWARN\t(HSTS is not expected on the intentionally HTTP-only ephemeral CI target)\n10036\tWARN\t(Server header information disclosure requires triage)\n10038\tWARN\t(CSP findings remain visible while the API landing page policy is hardened)\n""",
)
write(
    ".zap/api-rules.tsv",
    """10020\tWARN\t(Anti-clickjacking is a Web UI concern; API responses remain reported)\n10021\tFAIL\t(X-Content-Type-Options must be nosniff)\n10023\tFAIL\t(API debug/error disclosure is blocking)\n10035\tWARN\t(HSTS is not expected on the intentionally HTTP-only ephemeral CI target)\n10036\tWARN\t(Server header information disclosure requires triage)\n10038\tWARN\t(CSP is not an API-response blocking criterion)\n40018\tFAIL\t(SQL Injection)\n90020\tFAIL\t(Remote OS Command Injection)\n""",
)

zap_workflow = '''---
name: OWASP ZAP Web and API

on:
  pull_request:
    branches: [master]
    types: [opened, synchronize, reopened, ready_for_review]
    paths:
      - "nabla/**"
      - "server_all.py"
      - "templates/**"
      - ".zap/**"
      - ".github/workflows/security-zap.yml"
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: zap-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  dast:
    name: ZAP Web + OpenAPI on ephemeral runtime
    if: ${{ github.event_name != 'pull_request' || github.event.pull_request.draft == false }}
    runs-on: ubuntu-latest
    timeout-minutes: 25
    env:
      PYTHON_VERSION: "3.13"
      BASE_URL: "http://127.0.0.1:8080"
      KEYCLOAK_SERVER_URL: http://localhost:18080
      KEYCLOAK_REALM: test
      KEYCLOAK_CLIENT_ID: test
      KEYCLOAK_CLIENT_SECRET: test-secret
      OAUTH_TOKEN_SECRET: mocked-oauth-token-secret
      FASTAPI_RUNTIME_MODE: local
      SICKZ_INTERNAL_NETWORK: "true"
      HOMELAB_INTERNAL_PROBES_ENABLED: "false"
      METRICS_ENABLED: "false"
      LOGFIRE_ENABLED: "false"
      LOGFIRE_TOKEN: ""
      SENTRY_ENABLED: "false"
      SENTRY_DSN: ""
      DATADOG_ENABLED: "false"
      DD_TRACE_ENABLED: "false"
      DD_PROFILING_ENABLED: "false"
      DD_LOGS_INJECTION: "false"
      DD_APPSEC_ENABLED: "false"
      DD_IAST_ENABLED: "false"
      UNLEASH_ENABLED: "false"
      STATSIG_ENABLED: "false"

    steps:
      - name: Checkout exact PR SHA
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 1
          persist-credentials: false

      - name: Set up Python
        uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Install uv
        uses: astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d # v10.0.1
        with:
          enable-cache: true
          python-version: ${{ env.PYTHON_VERSION }}
          version: "0.12.1"

      - name: Install locked application dependencies
        run: uv sync --frozen

      - name: Start isolated FastAPI runtime
        shell: bash
        run: |
          set -euo pipefail
          nohup uv run uvicorn server_all:app --host 127.0.0.1 --port 8080 > /tmp/fastapi-zap.log 2>&1 &
          echo "$!" > /tmp/fastapi-zap.pid
          for attempt in $(seq 1 60); do
            if curl --fail --silent --show-error "$BASE_URL/health" >/dev/null; then
              echo "FastAPI DAST target ready after ${attempt}s."
              curl --fail --silent --show-error "$BASE_URL/openapi.json" >/dev/null
              exit 0
            fi
            sleep 1
          done
          cat /tmp/fastapi-zap.log
          echo "::error::FastAPI DAST target did not become ready."
          exit 1

      - name: OWASP ZAP Web baseline
        id: zap_web
        continue-on-error: true
        uses: zaproxy/action-baseline@de8ad967d3548d44ef623df22cf95c3b0baf8b25 # v0.15.0
        with:
          docker_name: ghcr.io/zaproxy/zaproxy:2.17.0
          target: ${{ env.BASE_URL }}/api
          rules_file_name: ".zap/web-rules.tsv"
          allow_issue_writing: false
          fail_action: true
          artifact_name: zap-web-report
          cmd_options: "-I -T 5 -c .zap/web-rules.tsv"

      - name: OWASP ZAP OpenAPI active scan
        id: zap_api
        continue-on-error: true
        uses: zaproxy/action-api-scan@5158fe4d9d8fcc75ea204db81317cce7f9e5453d # v0.10.0
        with:
          docker_name: ghcr.io/zaproxy/zaproxy:2.17.0
          target: ${{ env.BASE_URL }}/openapi.json
          format: openapi
          rules_file_name: ".zap/api-rules.tsv"
          allow_issue_writing: false
          fail_action: true
          artifact_name: zap-api-report
          cmd_options: "-I -T 5 -c .zap/api-rules.tsv"

      - name: Summarize ZAP outcomes
        if: always()
        env:
          WEB_OUTCOME: ${{ steps.zap_web.outcome }}
          API_OUTCOME: ${{ steps.zap_api.outcome }}
        shell: bash
        run: |
          {
            echo "## OWASP ZAP DAST"
            echo
            echo "- Exact source SHA: \`${GITHUB_SHA}\`"
            echo "- Web baseline: **${WEB_OUTCOME:-not-run}** · \`/api\`"
            echo "- OpenAPI active scan: **${API_OUTCOME:-not-run}** · \`/openapi.json\`"
            echo "- Target: isolated runner-local FastAPI process; no production/TrueNAS/pfSense target is attacked."
            echo "- Artifacts: \`zap-web-report\`, \`zap-api-report\`"
          } >> "$GITHUB_STEP_SUMMARY"

      - name: Enforce ZAP Web and API policy
        if: always()
        env:
          WEB_OUTCOME: ${{ steps.zap_web.outcome }}
          API_OUTCOME: ${{ steps.zap_api.outcome }}
        shell: bash
        run: |
          if [[ "$WEB_OUTCOME" != "success" || "$API_OUTCOME" != "success" ]]; then
            echo "::error::ZAP Web/API DAST did not satisfy the blocking policy. Inspect both report artifacts."
            exit 1
          fi

      - name: Show application log on failure
        if: failure()
        shell: bash
        run: cat /tmp/fastapi-zap.log || true
'''
write(".github/workflows/security-zap.yml", zap_workflow)


# 8. Contract tests for the anti-flicker behavior and DAST topology.
write(
    "tests/unit/test_ui_refresh_stability_contract.py",
    '''"""Static contracts for stable operator refresh and collapsed technical panels."""\n\nfrom pathlib import Path\n\nROOT = Path(__file__).resolve().parents[2]\n\n\ndef test_service_board_precedes_technical_drilldowns_and_runtime_is_collapsed() -> None:\n    ui = (ROOT / "nabla/api/ui.py").read_text(encoding="utf-8")\n    assert ui.index('class="health-board"') < ui.index('class="truenas-platform"')\n    assert ui.index('class="truenas-platform"') < ui.index('class="runtime-topology"')\n    runtime_line = next(line for line in ui.splitlines() if 'id="runtime-topology"' in line)\n    assert " open " not in runtime_line\n\n\ndef test_automatic_refresh_does_not_reload_collapsed_technical_drilldowns() -> None:\n    javascript = (ROOT / "nabla/api/assets/api-health.js").read_text(encoding="utf-8")\n    assert "includeTechnical = false" in javascript\n    assert "loadHealthBoards({ includeTechnical: true })" in javascript\n    assert "technicalDetailsOpen()" in javascript\n    assert 'id="runtime-topology"' in javascript\n    assert 'id="truenas-probe-dashboard"' in javascript\n\n\ndef test_fanout_and_advisory_pfsense_telemetry_are_collapsible() -> None:\n    fanout = (ROOT / "nabla/api/assets/api-probe-fanout-dashboard.js").read_text(encoding="utf-8")\n    truenas = (ROOT / "nabla/api/assets/api-truenas.js").read_text(encoding="utf-8")\n    assert 'document.createElement("details")' in fanout\n    assert "if (!root.open)" in fanout\n    assert "Refresh details" in fanout\n    assert 'container = document.createElement("details")' in truenas\n    assert "container.open = wasOpen" in truenas\n    assert "container.open = true" in truenas\n\n\ndef test_service_and_exposure_lists_have_stable_render_guards() -> None:\n    health = (ROOT / "nabla/api/assets/api-health-core.js").read_text(encoding="utf-8")\n    sickz = (ROOT / "nabla/api/assets/api-sickz.js").read_text(encoding="utf-8")\n    assert "lastHealthRowsSignature" in health\n    assert "signature === lastHealthRowsSignature" in health\n    assert "lastSickzRowsSignature" in sickz\n    assert "signature === lastSickzRowsSignature" in sickz\n''',
)

write(
    "tests/unit/test_zap_workflow_contract.py",
    '''"""Security contracts for the dual Web/OpenAPI ZAP workflow."""\n\nfrom pathlib import Path\n\nROOT = Path(__file__).resolve().parents[2]\nWORKFLOW = ROOT / ".github/workflows/security-zap.yml"\n\n\ndef test_zap_scans_web_and_openapi_on_ephemeral_local_runtime() -> None:\n    workflow = WORKFLOW.read_text(encoding="utf-8")\n    assert "OWASP ZAP Web baseline" in workflow\n    assert "OWASP ZAP OpenAPI active scan" in workflow\n    assert "zaproxy/action-baseline@de8ad967d3548d44ef623df22cf95c3b0baf8b25" in workflow\n    assert "zaproxy/action-api-scan@5158fe4d9d8fcc75ea204db81317cce7f9e5453d" in workflow\n    assert "${{ env.BASE_URL }}/api" in workflow\n    assert "${{ env.BASE_URL }}/openapi.json" in workflow\n    assert "format: openapi" in workflow\n    assert "127.0.0.1:8080" in workflow\n    assert "fastapi-sample.fastapicloud.dev/openapi.json" not in workflow\n    assert "home.albandrieu.com:10443" not in workflow\n\n\ndef test_zap_policy_distinguishes_web_and_api_findings() -> None:\n    workflow = WORKFLOW.read_text(encoding="utf-8")\n    assert '.zap/web-rules.tsv' in workflow\n    assert '.zap/api-rules.tsv' in workflow\n    assert "zap-web-report" in workflow\n    assert "zap-api-report" in workflow\n    assert "WEB_OUTCOME" in workflow and "API_OUTCOME" in workflow\n''',
)


# 9. Record durable follow-up before an agent can claim completion.
path = "docs/engineering-roadmap.md"
text = read(path)
marker = "## P1 — Runtime stability and appliance protection"
roadmap = '''### UI refresh stability + dual ZAP DAST follow-up (PR #237)\n\n- [x] Prioritize service outcomes before TrueNAS/runtime drill-downs and collapse FastAPI Cloud runtime plus homelab fan-out details by default.\n- [x] Decouple high-frequency service polling from TrueNAS/runtime technical refresh and skip destructive service/exposure DOM rebuilds when semantic state is unchanged.\n- [x] Run OWASP ZAP Web baseline and OpenAPI active DAST against an isolated runner-local FastAPI instance for PR application changes; never active-scan pfSense/TrueNAS production APIs from this job.\n- [ ] After the first successful PR ZAP execution, review the Web/API artifacts and tune only documented false positives in `.zap/web-rules.tsv` / `.zap/api-rules.tsv`; scanner/configuration failures must remain distinct from zero findings.\n- [ ] Consider a post-deploy **passive Web baseline** against FastAPI Cloud once the production deployment gate is healthy. Keep active OpenAPI attacks on isolated disposable targets unless an explicit non-production remote DAST environment is introduced.\n\n'''
if "### UI refresh stability + dual ZAP DAST follow-up (PR #237)" not in text:
    text = replace_once(text, marker, roadmap + marker, label="roadmap ZAP/UI follow-up")
write(path, text)

print("PR #237 UI stability + dual ZAP patch prepared")
