const CLOUDFLARE_ICON =
  "https://cdn.jsdelivr.net/gh/selfhst/icons@main/svg/cloudflare.svg";

let latestChecks = null;
let installed = false;
let scheduled = false;

function normalize(value) {
  return String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

function hostOf(value) {
  if (!value) return "";
  try {
    return new URL(String(value), window.location.href).hostname.toLowerCase();
  } catch {
    return "";
  }
}

function matchesRow(check, row) {
  const key = normalize(row.dataset.serviceKey);
  const name = normalize(row.dataset.serviceName);
  const ids = [check?.service_id, check?.serviceId, check?.id]
    .map(normalize)
    .filter(Boolean);
  if (key && ids.includes(key)) return true;
  const names = [check?.name, check?.display_label]
    .map(normalize)
    .filter(Boolean);
  if (name && names.includes(name)) return true;
  const rowHost = hostOf(row.dataset.serviceUrl);
  const aliases = Array.isArray(check?.aliases_probed)
    ? check.aliases_probed
    : [];
  const hosts = [check?.url, check?.tunnel_url, check?.tunnelUrl, ...aliases]
    .map(hostOf)
    .filter(Boolean);
  return Boolean(rowHost && hosts.includes(rowHost));
}

function tunnelState(check) {
  const observed = check.cloudflare_tunnel_observed;
  const status = String(check.cloudflare_tunnel_status || "").toUpperCase();
  const observerConfigured =
    check.cloudflare_tunnel_observer_configured === true;
  const observerError = String(
    check.cloudflare_tunnel_observer_error || "",
  ).trim();
  const edgeObserved =
    check.cloudflare_http_evidence === true ||
    check.cloudflare_edge_observed === true ||
    check.cloudflare_edge_headers_observed === true;

  if (
    observed === true &&
    (!status || ["HEALTHY", "ACTIVE", "UP"].includes(status))
  ) {
    return [
      "ok",
      "Cloudflare Tunnel configured",
      status
        ? `Tunnel ingress observed (${status})`
        : "Tunnel ingress observed",
    ];
  }
  if (observed === true) {
    return [
      "warn",
      "Cloudflare Tunnel degraded",
      `Tunnel ingress reports ${status || "an uncertain state"}`,
    ];
  }
  if (observerConfigured && !observerError && !edgeObserved) {
    return [
      "fail",
      "Cloudflare Tunnel missing",
      "tunnelSecure=true but no matching authoritative Tunnel ingress was observed",
    ];
  }
  if (edgeObserved) {
    return [
      "warn",
      "Cloudflare Tunnel unverified",
      "Cloudflare edge traffic is observed, but matching Tunnel ingress is not confirmed",
    ];
  }
  return [
    "warn",
    "Cloudflare Tunnel unverified",
    observerError
      ? `Tunnel inventory could not be verified (${observerError})`
      : "Tunnel inventory is unavailable or inconclusive",
  ];
}

function policyDetail(check) {
  const parts = [];
  const names = Array.isArray(check.cloudflare_access_policy_names)
    ? check.cloudflare_access_policy_names.filter(Boolean)
    : [];
  const decisions = Array.isArray(check.cloudflare_access_policy_decisions)
    ? check.cloudflare_access_policy_decisions.filter(Boolean)
    : [];
  const count = Number(check.cloudflare_access_policy_count);
  if (names.length > 0) parts.push(`Access policies: ${names.join(", ")}`);
  else if (Number.isFinite(count)) {
    parts.push(`${count} Access polic${count === 1 ? "y" : "ies"}`);
  }
  if (decisions.length > 0) parts.push(`decisions=${decisions.join(", ")}`);
  if (check.cloudflare_default_deny === true) {
    parts.push("Default-Deny observed");
  }
  if (check.cloudflare_service_auth_attempted === true) {
    const status = Number(check.cloudflare_service_token_http_status);
    const result =
      check.cloudflare_service_token_access_passed === true
        ? "passed"
        : "blocked";
    parts.push(
      `Service token ${result}${Number.isFinite(status) ? ` (HTTP ${status})` : ""}`,
    );
  }
  return parts.join(" · ");
}

function replaceCloudflareIcon(badge) {
  const current = badge.querySelector(".service-probe-icon");
  if (current?.tagName === "IMG" && current.src === CLOUDFLARE_ICON) return;
  const icon = document.createElement("img");
  icon.className = "service-probe-icon service-probe-icon--image";
  icon.src = CLOUDFLARE_ICON;
  icon.alt = "";
  icon.width = 16;
  icon.height = 16;
  icon.loading = "lazy";
  icon.setAttribute("aria-hidden", "true");
  current?.replaceWith(icon);
}

function apply() {
  scheduled = false;
  if (!latestChecks) return;
  const checks = Object.values(latestChecks);
  for (const row of document.querySelectorAll(
    ".health-row[data-service-filter-target]",
  )) {
    for (const duplicate of row.querySelectorAll(".cloudflare-tunnel-badge")) {
      duplicate.remove();
    }
    const badge = row.querySelector(
      '.service-probe-strip [data-probe-kind="cloudflare"]',
    );
    if (!badge) continue;
    const check = checks.find((candidate) => matchesRow(candidate, row));
    if (!check) continue;

    const [tone, label, detail] = tunnelState(check);
    for (const candidate of ["ok", "warn", "fail", "unknown", "neutral"]) {
      badge.classList.remove(`service-probe--${candidate}`);
    }
    badge.classList.add(`service-probe--${tone}`);
    replaceCloudflareIcon(badge);
    const policy = policyDetail(check);
    const hover = [label, detail, policy].filter(Boolean).join(" · ");
    badge.title = hover;
    badge.setAttribute("aria-label", hover);
    const text = badge.querySelector(".service-probe-label");
    if (text) text.textContent = "Tunnel";
  }
}

function schedule() {
  if (scheduled) return;
  scheduled = true;
  window.setTimeout(() => window.requestAnimationFrame(apply), 0);
}

export function decorateCloudflareProbeStatuses(data) {
  latestChecks = data?.checks || {};
  if (!installed) {
    installed = true;
    document.addEventListener("health-board-refreshed", schedule);
  }
  schedule();
}
