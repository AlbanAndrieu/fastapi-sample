import { fetchHealthBoard } from "./api-health-board.js";
import { decorateHttpProbeStatuses } from "./api-http-probe-status.js";
import { firstObservedCheck } from "./api-service-http-auth.js";
import { serviceTelemetry } from "./api-service-telemetry.js";

const ROW_SELECTOR = ".health-row[data-service-filter-target]";
const CLOUDFLARE_DASHBOARD = "https://one.dash.cloudflare.com/";

let latestSnapshot = null;
let scheduled = false;

function normalize(value) {
  return String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

function hostOf(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const candidate = raw.includes("://")
    ? raw
    : `https://${raw.replace(/^\/+/, "")}`;
  try {
    return new URL(candidate).hostname.toLowerCase().replace(/\.$/, "");
  } catch {
    return "";
  }
}

function collectionValues(collection) {
  if (Array.isArray(collection)) return collection;
  if (collection && typeof collection === "object") {
    return Object.values(collection);
  }
  return [];
}

function checkMatchesRow(check, row) {
  if (!check || !row) return false;
  const key = normalize(row.dataset.serviceKey);
  const name = normalize(row.dataset.serviceName);
  const ids = [check.id, check.service_id, check.serviceId]
    .map(normalize)
    .filter(Boolean);
  if (key && ids.includes(key)) return true;
  const names = [check.name, check.display_label]
    .map(normalize)
    .filter(Boolean);
  if (name && names.includes(name)) return true;

  const rowHost = hostOf(row.dataset.serviceUrl);
  const aliases = Array.isArray(check.aliases_probed)
    ? check.aliases_probed
    : [];
  return [check.url, check.tunnel_url, check.tunnelUrl, check.href, ...aliases]
    .map(hostOf)
    .filter(Boolean)
    .includes(rowHost);
}

function findCheck(collection, row) {
  return (
    collectionValues(collection).find((check) => checkMatchesRow(check, row)) ||
    null
  );
}

function exposureForRow(snapshot, row) {
  const checks = snapshot?.sickz?.checks || {};
  const direct = checks[row.dataset.serviceKey];
  return direct || findCheck(checks, row);
}

function publicForRow(snapshot, row) {
  const declared = findCheck(snapshot?.homelab?.services, row);
  const rowHost = hostOf(row.dataset.serviceUrl);
  // A catalogue entry for another hostname must not speak for this endpoint.
  const declaredHere =
    rowHost && hostOf(declared?.url) && hostOf(declared.url) !== rowHost
      ? null
      : declared;
  return firstObservedCheck(
    findCheck(snapshot?.homelab?.public_probe_results, row),
    declaredHere,
  );
}

function internalForRow(snapshot, row) {
  return findCheck(snapshot?.homelab?.internal_services, row);
}

function localPlanesEnabled(snapshot) {
  const mode = String(snapshot?.runtime?.runtime_mode || "").toLowerCase();
  return mode === "homelab" || mode === "local";
}

function publicUrl(row, exposure, publicCheck) {
  return (
    publicCheck?.url ||
    exposure?.tunnel_url ||
    exposure?.tunnelUrl ||
    exposure?.href ||
    row.dataset.serviceUrl ||
    ""
  );
}

function cloudflareRoute(summary, hostname) {
  if (!hostname) return null;
  for (const tunnel of summary?.tunnels || []) {
    const route = (tunnel?.ingress || []).find(
      (candidate) => normalize(candidate?.hostname) === normalize(hostname),
    );
    if (route) return { tunnel, route };
  }
  return null;
}

function accessApplication(summary, hostname) {
  if (!hostname) return null;
  return (summary?.access_applications || []).find((application) => {
    const domain = String(application?.domain || "").trim();
    const domainHost = hostOf(domain);
    return (
      domainHost === hostname ||
      normalize(domain) === normalize(hostname) ||
      normalize(domain).startsWith(`${normalize(hostname)}/`)
    );
  });
}

function toneClass(node, tone) {
  // Unchanged tone: touch nothing, observers would re-render the card.
  if (node.classList.contains(`service-probe--${tone}`)) return;
  for (const candidate of [
    "ok",
    "warn",
    "fail",
    "unknown",
    "neutral",
    "info",
    "expected",
  ]) {
    node.classList.remove(`service-probe--${candidate}`);
  }
  node.classList.add(`service-probe--${tone}`);
}

function badgeLabel(node, label) {
  const text = node.querySelector(".service-probe-label");
  if (text && text.textContent !== label) text.textContent = label;
}

function linkedBadge(node, href) {
  if (!node || !href) return node;
  if (node.tagName === "A") {
    node.href = href;
    node.target = "_blank";
    node.rel = "noopener noreferrer";
    return node;
  }
  const link = document.createElement("a");
  for (const attribute of node.attributes) {
    link.setAttribute(attribute.name, attribute.value);
  }
  link.href = href;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.style.textDecoration = "none";
  while (node.firstChild) link.appendChild(node.firstChild);
  node.replaceWith(link);
  return link;
}

function ensureProbe(strip, kind, icon, label) {
  let badge = strip.querySelector(`[data-probe-kind="${kind}"]`);
  if (!badge) {
    badge = document.createElement("span");
    badge.className = "service-probe service-probe--unknown";
    badge.dataset.probeKind = kind;
    const iconNode = document.createElement("span");
    iconNode.className = "service-probe-icon";
    iconNode.setAttribute("aria-hidden", "true");
    iconNode.textContent = icon;
    const text = document.createElement("span");
    text.className = "service-probe-label";
    text.textContent = label;
    badge.append(iconNode, text);
    strip.appendChild(badge);
  }
  badgeLabel(badge, label);
  return badge;
}

function ensurePlaneLabel(primary, strip, plane, label, href, detail) {
  let node = primary.querySelector(
    `:scope > .service-probe-plane-label--${plane}`,
  );
  if (!node) {
    node = document.createElement("div");
    node.className = `service-probe-plane-label service-probe-plane-label--${plane}`;
    primary.insertBefore(node, strip);
  }
  // Unchanged inputs: keep the node (api-health-ui-operator-followup links it).
  const key = JSON.stringify([label, href || "", detail || ""]);
  if (node.dataset.planeKey === key) return;
  node.dataset.planeKey = key;
  node.replaceChildren();
  const title = document.createElement("strong");
  title.textContent = label;
  node.appendChild(title);
  if (href) {
    const link = document.createElement("a");
    link.href = href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = href;
    link.title = detail || href;
    node.appendChild(link);
  } else if (detail) {
    const text = document.createElement("span");
    text.textContent = detail;
    node.appendChild(text);
  }
}

function decoratePublicEvidence(strip, check, url) {
  if (!check) return;
  // api-http-probe-status.js alone tones, labels and titles this badge: two
  // writers with different evidence made it flip on every refresh.
  if (!strip.querySelector('[data-probe-kind="http"]')) {
    ensureProbe(strip, "http", "🌐", "HTTP");
  }

  const tls = ensureProbe(strip, "tls", "🔒", "TLS");
  const tlsTone =
    check.tls_trusted === true
      ? "ok"
      : check.tls_trusted === false
        ? "fail"
        : "unknown";
  toneClass(tls, tlsTone);
  const tlsDetail =
    check.tls_trusted === true
      ? `TLS certificate validated for ${url || check.url || "public target"}`
      : check.tls_trusted === false
        ? `TLS validation failed for ${url || check.url || "public target"}`
        : `TLS state unconfirmed for ${url || check.url || "public target"}`;
  tls.title = tlsDetail;
  tls.setAttribute("aria-label", tlsDetail);
}

function decorateCloudflare(strip, summary, exposure, hostname) {
  const matchedRoute = cloudflareRoute(summary, hostname);
  const tunnelState =
    matchedRoute?.tunnel?.status ||
    exposure?.cloudflare_tunnel_status ||
    "unknown";
  const tunnelObserved = Boolean(
    matchedRoute || exposure?.cloudflare_tunnel_observed === true,
  );
  let tunnel = ensureProbe(strip, "cloudflare", "☁️", "Tunnel");
  const origin =
    matchedRoute?.route?.service ||
    exposure?.cloudflare_origin_service ||
    "origin unconfirmed";
  const tunnelDetail = tunnelObserved
    ? `Cloudflare Tunnel / Published application route: ${hostname || "hostname"} → ${origin} · tunnel=${matchedRoute?.tunnel?.name || exposure?.cloudflare_tunnel_name || "observed"} · status=${tunnelState}. Tunnel provides routing/connectivity; it does not authorize users.`
    : "Cloudflare Tunnel / Published application route is unverified. Tunnel provides routing/connectivity; Access is the separate authorization layer.";
  // api-cloudflare-probe owns the badge once it has /sickz evidence.
  if (tunnel.dataset.statusOwner !== "cloudflare-probe") {
    toneClass(
      tunnel,
      tunnelObserved
        ? normalize(tunnelState) === "healthy"
          ? "ok"
          : "warn"
        : "unknown",
    );
    if (tunnel.title !== tunnelDetail) {
      tunnel.title = tunnelDetail;
      tunnel.setAttribute("aria-label", tunnelDetail);
    }
  }
  if (hostname) {
    tunnel = linkedBadge(tunnel, CLOUDFLARE_DASHBOARD);
  }

  const app = accessApplication(summary, hostname);
  const policyCount = Number(
    exposure?.cloudflare_access_policy_count ?? app?.policy_count,
  );
  const hasAccess = Boolean(
    app ||
      exposure?.cloudflare_access_observed === true ||
      Number.isFinite(policyCount),
  );
  if (hasAccess) {
    let access = ensureProbe(strip, "access", "🛡️", "Access");
    toneClass(access, app || policyCount > 0 ? "ok" : "warn");
    const policies = app?.policies || [];
    const accessDetail = `Cloudflare Access application: authorization layer for ${hostname || "this hostname"}${Number.isFinite(policyCount) ? ` · ${policyCount} polic${policyCount === 1 ? "y" : "ies"}` : ""}${policies.length ? ` · ${policies.map((policy) => `${policy.name} (${policy.decision})`).join(", ")}` : ""}. Access decides who may enter; the Tunnel decides where authorized traffic is routed.`;
    access.title = accessDetail;
    access.setAttribute("aria-label", accessDetail);
    access = linkedBadge(access, CLOUDFLARE_DASHBOARD);
  }

  const control = summary?.control_plane?.access_service_tokens || {};
  const attempted = exposure?.cloudflare_service_auth_attempted === true;
  const passed = exposure?.cloudflare_service_token_access_passed;
  if (attempted || control.configured_client_id_present != null) {
    let token = ensureProbe(strip, "service-token", "🔑", "Token");
    const tone =
      passed === true
        ? "ok"
        : passed === false
          ? "fail"
          : control.configured_client_id_present === true
            ? "unknown"
            : "warn";
    toneClass(token, tone);
    const status = Number(exposure?.cloudflare_service_token_http_status);
    const tokenDetail = attempted
      ? `Cloudflare Access Service Token live check: ${passed === true ? "passed" : passed === false ? "blocked" : "unconfirmed"}${Number.isFinite(status) ? ` · HTTP ${status}` : ""}. The token is a machine identity used by an Access Service Auth policy; it does not define the Tunnel route.`
      : `Configured Cloudflare Access Service Token ${control.configured_client_id_present === true ? "is present" : "is not confirmed"} in the read-only inventory. No per-service live Service Auth result is available in this snapshot.`;
    token.title = tokenDetail;
    token.setAttribute("aria-label", tokenDetail);
    token = linkedBadge(token, CLOUDFLARE_DASHBOARD);
  }
}

function internalEndpoint(check, exposure) {
  const origin = String(exposure?.cloudflare_origin_service || "").trim();
  if (/^https?:\/\//i.test(origin)) return { label: origin, href: origin };
  if (check?.host && check?.port != null) {
    return { label: `${check.host}:${check.port}`, href: "" };
  }
  return { label: "LAN target unavailable", href: "" };
}

function ensureLanStrip(primary) {
  let strip = primary.querySelector(
    ':scope > .service-probe-strip[data-probe-plane="lan"]',
  );
  if (!strip) {
    strip = document.createElement("div");
    strip.className =
      "service-probe-strip service-probe-strip--plane service-probe-strip--lan";
    strip.dataset.probePlane = "lan";
    primary.appendChild(strip);
  }
  return strip;
}

const LAN_KINDS = [
  "tcp",
  "prometheus",
  "gatus",
  "gatus-fleet",
  "exporter",
  "flow",
  "functional",
  "resource",
];

function decorateLan(primary, check, exposure, snapshot, row) {
  const strip = ensureLanStrip(primary);
  const endpoint = internalEndpoint(check, exposure);
  ensurePlaneLabel(primary, strip, "lan", "LAN", endpoint.href, endpoint.label);
  // Built off-DOM, then only changed badges are swapped: clearing the strip
  // on every pass made each LAN badge blink.
  const fresh = document.createElement("div");
  fillLan(fresh, check, endpoint, snapshot, row);
  const kinds = new Set(
    [...fresh.children].map((badge) => badge.dataset.probeKind),
  );
  for (const badge of [...fresh.children]) {
    const current = strip.querySelector(
      `:scope > [data-probe-kind="${badge.dataset.probeKind}"]`,
    );
    if (
      current &&
      current.className === badge.className &&
      current.textContent === badge.textContent
    ) {
      // api-health-ui-probe-explanations titles an unsampled (unknown) TCP probe.
      const explained =
        badge.dataset.probeKind === "tcp" &&
        badge.classList.contains("service-probe--unknown");
      if (!explained && current.title !== badge.title) {
        current.title = badge.title;
        current.setAttribute("aria-label", badge.title);
      }
      continue;
    }
    if (current) current.replaceWith(badge);
    else strip.appendChild(badge);
  }
  for (const node of strip.querySelectorAll(":scope > [data-probe-kind]")) {
    if (
      LAN_KINDS.includes(node.dataset.probeKind) &&
      !kinds.has(node.dataset.probeKind)
    )
      node.remove();
  }
}

function fillLan(strip, check, endpoint, snapshot, row) {
  const tcp = ensureProbe(strip, "tcp", "🔌", "TCP");
  const tone =
    check?.reachable === true
      ? "ok"
      : check?.reachable === false
        ? "fail"
        : "unknown";
  toneClass(tcp, tone);
  const detail = check
    ? `LAN connectivity probe: ${endpoint.label} · ${check.reachable === true ? "reachable" : check.reachable === false ? "unreachable" : "unconfirmed"}${check.latency_ms != null ? ` · ${check.latency_ms} ms` : ""}`
    : `LAN probe not sampled yet: ${endpoint.label}. Enable HOMELAB_INTERNAL_PROBES_ENABLED=true on trusted homelab/local runtimes to collect this evidence.`;
  tcp.title = detail;
  tcp.setAttribute("aria-label", detail);
  decorateTelemetry(strip, snapshot, row);
}

function decorateTelemetry(strip, snapshot, row) {
  const evidence = serviceTelemetry(snapshot, row);
  for (const [kind, icon, entry] of [
    ["prometheus", "📈", evidence.prometheus],
    ["gatus", "🩺", evidence.gatus],
    ["gatus-fleet", "🧪", evidence.gatusFleet],
    ["exporter", "📊", evidence.exporter],
    ["flow", "🌊", evidence.flow],
    ["functional", "🗄️", evidence.functional],
    ["resource", "🧠", evidence.resource],
  ]) {
    if (!entry) continue;
    const badge = ensureProbe(strip, kind, icon, entry.label);
    toneClass(badge, entry.tone);
    badge.title = entry.detail;
    badge.setAttribute("aria-label", entry.detail);
  }
}

function decorateIssueSummary(row, strip) {
  // One visible summary per card, based only on existing read-only badges.
  const observations = [...row.querySelectorAll(".service-probe")].filter(
    (probe) =>
      probe.dataset.probeKind !== "issues" &&
      probe.dataset.probeDisabled !== "true",
  );
  const failures = observations.filter((item) =>
    item.classList.contains("service-probe--fail"),
  );
  const warnings = observations.filter((item) =>
    item.classList.contains("service-probe--warn"),
  );
  if (!failures.length && !warnings.length) {
    strip.querySelector('[data-probe-kind="issues"]')?.remove();
    return;
  }
  const label = `${failures.length} failed · ${warnings.length} warning`;
  const badge = ensureProbe(strip, "issues", "⚠️", label);
  toneClass(badge, failures.length ? "fail" : "warn");
  const summary = [...failures, ...warnings]
    .slice(0, 4)
    .map(
      (item) =>
        item.querySelector(".service-probe-label")?.textContent?.trim() ||
        item.dataset.probeKind ||
        "probe",
    );
  const detail = `Observed diagnostic badge issues: ${summary.join(", ")}. Open Details for HTTP, DNS, TLS, Token and metrics evidence; this is not an overall service-down verdict.`;
  badge.title = detail;
  badge.setAttribute("aria-label", detail);
}

function cleanLegacyText(row, exposure) {
  const tags = row.querySelector(".health-row-tags");
  if (!tags) return;
  for (const badge of tags.querySelectorAll(
    "[data-operator-probe='external']",
  )) {
    badgeLabel(badge, "external");
    toneClass(badge, exposure?.external === false ? "neutral" : "ok");
  }
  const textNodes = [...tags.childNodes].filter(
    (node) => node.nodeType === Node.TEXT_NODE,
  );
  for (const node of textNodes) {
    node.textContent = String(node.textContent || "")
      .replace(/\bexternal=(?:true|false)\s*·?\s*/gi, "")
      .replace(/^\s*·\s*|\s*·\s*$/g, "");
  }
}

function decorateRow(row, snapshot) {
  const primary = row.querySelector(".health-row-primary");
  if (!primary) return;
  const exposure = exposureForRow(snapshot, row);
  const publicCheck = publicForRow(snapshot, row);
  const internalCheck = internalForRow(snapshot, row);
  const url = publicUrl(row, exposure, publicCheck);
  const hostname = hostOf(url);
  let publicStrip = primary.querySelector(":scope > .service-probe-strip");
  if (!publicStrip) {
    publicStrip = document.createElement("div");
    publicStrip.className = "service-probe-strip";
    primary.appendChild(publicStrip);
  }
  publicStrip.classList.add(
    "service-probe-strip--plane",
    "service-probe-strip--public",
  );
  publicStrip.dataset.probePlane = "public";
  decoratePublicEvidence(publicStrip, publicCheck, url);
  decorateCloudflare(
    publicStrip,
    snapshot?.homelab?.cloudflare,
    exposure,
    hostname,
  );
  cleanLegacyText(row, exposure);

  if (localPlanesEnabled(snapshot)) {
    ensurePlaneLabel(
      primary,
      publicStrip,
      "public",
      "Public",
      url,
      "Externally published endpoint",
    );
    decorateLan(primary, internalCheck, exposure, snapshot, row);
  } else {
    // Cloud has no LAN vantage. Reuse the single bounded Prometheus snapshot
    // in the public strip so metrics remain visible without a fake LAN probe.
    decorateTelemetry(publicStrip, snapshot, row);
    primary
      .querySelector(":scope > .service-probe-plane-label--public")
      ?.remove();
    primary.querySelector(":scope > .service-probe-plane-label--lan")?.remove();
    primary
      .querySelector(':scope > .service-probe-strip[data-probe-plane="lan"]')
      ?.remove();
  }
  decorateIssueSummary(row, publicStrip);
}

function apply() {
  scheduled = false;
  if (!latestSnapshot) return;
  for (const row of document.querySelectorAll(ROW_SELECTOR)) {
    decorateRow(row, latestSnapshot);
  }
  // A just-created HTTP badge gets its tone from the badge's sole owner.
  decorateHttpProbeStatuses(latestSnapshot);
}

function schedule() {
  if (scheduled) return;
  scheduled = true;
  window.setTimeout(() => window.requestAnimationFrame(apply), 0);
}

async function refresh() {
  latestSnapshot = await fetchHealthBoard().catch(() => latestSnapshot);
  schedule();
}

export function installServiceProbePlanes() {
  document.addEventListener("health-board-refreshed", refresh);
  refresh();
}
