const CLOUDFLARE_ICON =
  "https://cdn.jsdelivr.net/gh/selfhst/icons@main/svg/cloudflare.svg";

function setPending(summaryId, ledId, textId, label) {
  const summary = document.getElementById(summaryId);
  const led = document.getElementById(ledId);
  const text = document.getElementById(textId);
  if (!summary || !led || !text) return;
  summary.className =
    "health-summary health-summary--blue health-summary--pending";
  led.className = "health-led health-led--blue health-led--pending";
  text.textContent = `Pending — ${label} checks are running…`;
}

export function markHealthBoardsPending() {
  setPending(
    "health-summary",
    "health-summary-led",
    "health-summary-text",
    "health",
  );
  setPending(
    "sickz-summary",
    "sickz-summary-led",
    "sickz-summary-text",
    "exposure",
  );
}

function normalizeTunnelStatus(check) {
  if (check.tunnel_secure !== true) return null;

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
    return {
      cls: "green",
      label: "Cloudflare Tunnel configured",
      detail: status
        ? `Tunnel ingress observed (${status}).`
        : "Tunnel ingress hostname observed.",
    };
  }

  if (observed === true) {
    return {
      cls: "yellow",
      label: "Cloudflare Tunnel degraded",
      detail: `Tunnel ingress exists but reports ${status || "an uncertain state"}.`,
    };
  }

  if (observerConfigured && !observerError && !edgeObserved) {
    return {
      cls: "red",
      label: "Cloudflare Tunnel missing",
      detail:
        "tunnelSecure=true but the hostname is absent from the authoritative Tunnel ingress inventory.",
    };
  }

  if (edgeObserved) {
    return {
      cls: "yellow",
      label: "Cloudflare Tunnel unverified",
      detail:
        "Cloudflare edge traffic is observed, but the hostname is absent from the Tunnel ingress inventory. Check remote/local-managed tunnel configuration.",
    };
  }

  return {
    cls: "yellow",
    label: "Cloudflare Tunnel unverified",
    detail: observerError
      ? `Tunnel inventory could not be verified (${observerError}).`
      : "Tunnel inventory is unavailable or inconclusive.",
  };
}

function findRow(check) {
  const href = String(
    check.tunnel_url || check.tunnelUrl || check.href || "",
  ).trim();
  if (href) {
    const links = document.querySelectorAll("#sickz-checks .sickz-target-link");
    for (const link of links) {
      if (String(link.href).replace(/\/$/, "") === href.replace(/\/$/, "")) {
        return link.closest(".health-row");
      }
    }
  }
  const name = String(check.name || check.display_label || "")
    .trim()
    .toLowerCase();
  if (!name) return null;
  for (const row of document.querySelectorAll("#sickz-checks .health-row")) {
    const rowName = row
      .querySelector(".health-row-name")
      ?.textContent?.replace(/^⚠️\s*/, "")
      .trim()
      .toLowerCase();
    if (rowName === name) return row;
  }
  return null;
}

function replaceDirectProbeWording(row, check) {
  if (
    !row ||
    check.external !== true ||
    check.tunnel_secure !== false ||
    check.reachable !== false
  ) {
    return;
  }
  const href = String(check.tunnel_url || check.tunnelUrl || "");
  if (!href.includes(".int.albandrieu.com")) return;
  const detail = row.querySelector(".health-row-detail");
  if (!detail) return;
  detail.textContent = detail.textContent
    .replace(/→ unreachable(?:\s*\([^)]*\))?/i, "→ cloud probe inconclusive")
    .replace(/^Unreachable\.?/i, "Cloud probe inconclusive.");
  row.classList.add("health-row--probe-inconclusive");
}

function appendTunnelBadge(row, state) {
  if (!row || !state || row.querySelector(".cloudflare-tunnel-badge")) return;
  const tags =
    row.querySelector(".health-row-tags") ||
    row.querySelector(".health-row-main");
  if (!tags) return;
  const badge = document.createElement("span");
  badge.className = `cloudflare-tunnel-badge cloudflare-tunnel-badge--${state.cls}`;
  badge.title = `${state.label}: ${state.detail}`;
  badge.setAttribute("role", "img");
  badge.setAttribute("aria-label", `${state.label}. ${state.detail}`);
  badge.innerHTML = `<img src="${CLOUDFLARE_ICON}" alt="" width="18" height="18" loading="lazy"> <span>${state.label}</span>`;
  tags.appendChild(badge);
}

function decorate(data) {
  const checks = data?.checks || {};
  Object.values(checks).forEach((check) => {
    const row = findRow(check);
    replaceDirectProbeWording(row, check);
    appendTunnelBadge(row, normalizeTunnelStatus(check));
  });
}

export function decorateCloudflareTunnelStatuses() {
  fetch("/sickz", { headers: { Accept: "application/json" } })
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then((data) => {
      // api-sickz.js renders from the same endpoint. Defer one task so its rows exist.
      window.setTimeout(() => decorate(data), 0);
    })
    .catch(() => {
      // The primary sickz renderer owns fetch-error reporting. Do not duplicate it.
    });
}
