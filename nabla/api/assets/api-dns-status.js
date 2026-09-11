function normalize(value) {
  return String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

function slug(value) {
  return normalize(value)
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
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
  if (!check) return false;
  const rowIds = new Set(
    [
      row.dataset.serviceKey,
      String(row.dataset.serviceKey || "").replace(/^albandrieu_/, ""),
    ]
      .map(slug)
      .filter(Boolean),
  );
  const checkIds = [check.id, check.service_id, check.serviceId]
    .map(slug)
    .filter(Boolean);
  if (checkIds.some((value) => rowIds.has(value))) return true;

  if (normalize(check.name) === normalize(row.dataset.serviceName)) return true;

  const rowHost = hostOf(row.dataset.serviceUrl);
  return Boolean(rowHost && rowHost === hostOf(check.url));
}

function dnsChecks(snapshot) {
  const rows = [];
  for (const check of snapshot?.homelab?.services || []) rows.push(check);
  const truenas = snapshot?.homelab?.truenas?.public;
  if (truenas) rows.push({ ...truenas, id: "truenas", name: "TrueNAS HTTPS" });
  return rows.filter((check) => check?.dns_state || check?.dns_error);
}

function ensureProbeStrip(row) {
  const primary = row.querySelector(".health-row-primary");
  if (!primary) return null;
  let strip = primary.querySelector(":scope > .service-probe-strip");
  if (!strip) {
    strip = document.createElement("div");
    strip.className = "service-probe-strip";
    strip.setAttribute("aria-label", "Probe evidence");
    primary.appendChild(strip);
  }
  return strip;
}

function dnsDetail(check) {
  const state = String(check.dns_state || "unknown").toUpperCase();
  const parts = [`DNS ${state}`];
  if (check.dns_hostname) parts.push(`host ${check.dns_hostname}`);
  if (Number.isFinite(Number(check.dns_latency_ms))) {
    parts.push(`${Number(check.dns_latency_ms)} ms`);
  }
  const resolvers = Array.isArray(check.dns_resolvers)
    ? check.dns_resolvers.filter(Boolean)
    : [];
  if (resolvers.length > 0) {
    parts.push(`resolver ${resolvers.join(", ")}`);
  } else {
    parts.push("resolver not exposed by runtime");
  }
  const resolved = Array.isArray(check.dns_resolved)
    ? check.dns_resolved.filter(Boolean)
    : [];
  if (resolved.length > 0) parts.push(`answer ${resolved.join(", ")}`);
  if (check.dns_error) parts.push(`error ${check.dns_error}`);
  if (check.dns_probe) parts.push(`probe ${check.dns_probe}`);
  if (check.dns_resolver_source) {
    parts.push(`source ${check.dns_resolver_source}`);
  }
  return parts.join(" · ");
}

function badgeFor(check) {
  const state = String(check.dns_state || "unknown").toLowerCase();
  const tone = state === "ok" ? "ok" : state === "fail" ? "fail" : "unknown";
  const badge = document.createElement("span");
  badge.className = `service-probe service-probe--${tone} service-probe--operator`;
  badge.dataset.operatorProbe = "dns";
  badge.dataset.probeKind = "dns";
  const detail = dnsDetail(check);
  badge.title = detail;
  badge.setAttribute("aria-label", detail);

  const icon = document.createElement("span");
  icon.className = "service-probe-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = "🧭";
  const label = document.createElement("span");
  label.className = "service-probe-label";
  label.textContent = "DNS";
  badge.append(icon, label);
  return badge;
}

export function decorateDnsStatuses(snapshot) {
  const checks = dnsChecks(snapshot);
  for (const row of document.querySelectorAll(
    ".health-row[data-service-filter-target]",
  )) {
    const strip = ensureProbeStrip(row);
    if (!strip) continue;
    strip.querySelector('[data-operator-probe="dns"]')?.remove();
    const check = checks.find((candidate) => matchesRow(candidate, row));
    if (!check) continue;
    strip.prepend(badgeFor(check));
  }
}
