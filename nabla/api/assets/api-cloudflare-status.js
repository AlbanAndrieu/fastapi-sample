import { escapeText } from "./api-health-ui.js";

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

function cloudflarePolicyDetail(check) {
  const parts = [];
  const policyNames = Array.isArray(check.cloudflare_access_policy_names)
    ? check.cloudflare_access_policy_names.filter(Boolean)
    : [];
  const policyDecisions = Array.isArray(
    check.cloudflare_access_policy_decisions,
  )
    ? check.cloudflare_access_policy_decisions.filter(Boolean)
    : [];
  const policyCount = Number(check.cloudflare_access_policy_count);

  if (policyNames.length > 0) {
    parts.push(`Access policies: ${policyNames.join(", ")}`);
  } else if (Number.isFinite(policyCount)) {
    parts.push(
      `${policyCount} Access polic${policyCount === 1 ? "y" : "ies"} observed`,
    );
  }
  if (policyDecisions.length > 0) {
    parts.push(`decisions=${policyDecisions.join(", ")}`);
  }
  if (check.cloudflare_default_deny === true) {
    parts.push("Default-Deny observed");
  }
  if (check.cloudflare_service_auth_attempted === true) {
    const tokenStatus = Number(check.cloudflare_service_token_http_status);
    const tokenOutcome =
      check.cloudflare_service_token_access_passed === true
        ? "passed"
        : "blocked";
    parts.push(
      `Service token ${tokenOutcome}${Number.isFinite(tokenStatus) ? ` (HTTP ${tokenStatus})` : ""}`,
    );
  }
  return parts.join(" · ");
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

function appendTunnelBadge(row, state, check) {
  if (!row || !state || row.querySelector(".cloudflare-tunnel-badge")) return;
  const tags =
    row.querySelector(".health-row-tags") ||
    row.querySelector(".health-row-main");
  if (!tags) return;
  const badge = document.createElement("span");
  badge.className = `cloudflare-tunnel-badge cloudflare-tunnel-badge--${state.cls}`;
  const policyDetail = cloudflarePolicyDetail(check);
  const hover = [state.label, state.detail, policyDetail]
    .filter(Boolean)
    .join(" · ");
  badge.title = hover;
  badge.setAttribute("role", "img");
  badge.setAttribute("aria-label", hover);
  badge.innerHTML = `<img src="${CLOUDFLARE_ICON}" alt="" width="18" height="18" loading="lazy"> <span>Tunnel</span>`;
  tags.appendChild(badge);
}

function ensureTunnelStatusBlock() {
  let container = document.getElementById("cloudflare-tunnel-warning");
  if (container) return container;

  const ingress = document.getElementById("truenas-ingress-block");
  const target = ingress || document.getElementById("truenas-platform-target");
  if (!target) return null;

  container = document.createElement("details");
  container.id = "cloudflare-tunnel-warning";
  container.className = "truenas-ingress-block";
  target.insertAdjacentElement("afterend", container);
  return container;
}

function platformCloudflareDetail(platformCheck) {
  if (!platformCheck || platformCheck.status_confirmed === true) return null;
  const kind = String(platformCheck.error_kind || "unconfirmed").trim();
  const warning = String(
    platformCheck.warning ||
      platformCheck.error ||
      "Cloudflare control-plane status is unconfirmed",
  ).trim();
  const apiState =
    platformCheck.api_reachable === true
      ? "API reachable"
      : platformCheck.api_reachable === false
        ? "API unreachable"
        : "API reachability unknown";
  return `${apiState} · ${kind} · ${warning}`;
}

function exposureManagementDetail(exposureSummary) {
  if (!exposureSummary) return null;
  const local = Number(exposureSummary.local_managed_tunnels || 0);
  const remote = Number(exposureSummary.cloudflare_managed_tunnels || 0);
  const unknown = Number(exposureSummary.unknown_management_tunnels || 0);
  if (local > 0) {
    return `${local} local-managed tunnel(s) observed${remote > 0 ? ` · ${remote} dashboard-managed` : ""}${unknown > 0 ? ` · ${unknown} management mode unknown` : ""}. Local YAML ingress hostnames are not exposed by the remote Tunnel configuration API, so service-level tunnel verification can remain unverified even while cloudflared is healthy.`;
  }
  if (remote > 0 || unknown > 0) {
    return `${remote} dashboard-managed tunnel(s) · ${unknown} management mode unknown.`;
  }
  return null;
}

function tunnelInventoryDetails(exposureSummary) {
  if (!Array.isArray(exposureSummary?.tunnels)) return [];
  return exposureSummary.tunnels.map((tunnel) => {
    const name = String(tunnel?.name || "unnamed tunnel");
    const status = String(tunnel?.status || "unknown");
    const management = String(tunnel?.management || "unknown");
    const ingress = Array.isArray(tunnel?.ingress) ? tunnel.ingress : [];
    if (ingress.length === 0) {
      const visibility =
        tunnel?.ingress_visibility === "local_yaml_unavailable_via_api"
          ? "ingress owned by local cloudflared YAML; remote API cannot enumerate hostnames"
          : "no ingress hostname observed";
      return `Tunnel ${name} · ${status} · management=${management} · ${visibility}.`;
    }
    const routes = ingress
      .map((route) => {
        const routeStatus = route?.status ? ` · ${route.status}` : "";
        return `${route?.hostname || "hostname unknown"} → ${route?.service || "origin unknown"}${routeStatus}`;
      })
      .join("; ");
    return `Tunnel ${name} · ${status} · management=${management} · ${routes}.`;
  });
}

function accessInventoryDetails(exposureSummary) {
  if (!Array.isArray(exposureSummary?.access_applications)) return [];
  return exposureSummary.access_applications.map((application) => {
    const name = String(application?.name || "unnamed Access application");
    const domain = String(application?.domain || "domain unknown");
    const policies = Array.isArray(application?.policies)
      ? application.policies
      : [];
    const policyText = policies.length
      ? policies
          .map((policy) => {
            const everyone =
              policy?.includes_everyone === true ? " · everyone" : "";
            return `${policy?.name || "unnamed"}=${policy?.decision || "unknown"}${everyone}`;
          })
          .join(", ")
      : "no policy observed";
    return `Access ${name} · ${domain}${application?.path && application.path !== "/" ? application.path : ""} · policies: ${policyText}.`;
  });
}

function renderTunnelStatus(checks, platformCheck, exposureSummary) {
  const protectedChecks = Object.values(checks).filter(
    (check) => check?.tunnel_secure === true,
  );
  const unresolved = protectedChecks
    .map((check) => ({ check, state: normalizeTunnelStatus(check) }))
    .filter(({ state }) => state && state.cls !== "green");
  const platformDetail = platformCloudflareDetail(platformCheck);
  const managementDetail = exposureManagementDetail(exposureSummary);
  const tunnelDetails = tunnelInventoryDetails(exposureSummary);
  const accessDetails = accessInventoryDetails(exposureSummary);
  const container = ensureTunnelStatusBlock();
  if (!container) return;
  const hasInventory = tunnelDetails.length > 0 || accessDetails.length > 0;
  if (
    unresolved.length === 0 &&
    !platformDetail &&
    !managementDetail &&
    !hasInventory
  ) {
    container.hidden = true;
    container.open = false;
    container.innerHTML = "";
    return;
  }

  const warningState = unresolved.length > 0 || Boolean(platformDetail);
  const wasOpen = container.open === true;
  const observerErrors = [
    ...new Set(
      unresolved
        .map(({ check }) =>
          String(check.cloudflare_tunnel_observer_error || "").trim(),
        )
        .filter(Boolean),
    ),
  ];
  const edgeObserved = unresolved.filter(
    ({ check }) =>
      check.cloudflare_http_evidence === true ||
      check.cloudflare_edge_observed === true ||
      check.cloudflare_edge_headers_observed === true,
  ).length;
  const details = [];
  if (platformDetail) details.push(platformDetail);
  if (managementDetail) details.push(managementDetail);
  details.push(...tunnelDetails, ...accessDetails);
  if (observerErrors.length > 0) {
    details.push(
      `Tunnel inventory observer error: ${observerErrors.join(", ")}.`,
    );
  }
  if (edgeObserved > 0) {
    details.push(
      `${edgeObserved}/${unresolved.length} unresolved protected hostname(s) still show Cloudflare edge evidence.`,
    );
  }
  if (unresolved.length > 0) {
    details.push(
      `${unresolved.length} tunnel-protected hostname(s) are not confirmed by the current Tunnel ingress inventory.`,
    );
  }
  if (warningState) {
    details.push(
      "This is verification uncertainty, not proof that the service or Cloudflare Tunnel is down; check account/token scope and remote-vs-local tunnel management.",
    );
  }

  container.hidden = false;
  container.open = wasOpen;
  container.className = warningState
    ? "truenas-ingress-block truenas-ingress-block--warning"
    : "truenas-ingress-block";
  const heading = warningState
    ? "⚠ Cloudflare Tunnel verification temporarily unavailable"
    : "✓ Cloudflare Tunnel & Access status";
  container.innerHTML =
    '<summary><strong><img src="' +
    CLOUDFLARE_ICON +
    '" alt="" width="18" height="18" loading="lazy"> ' +
    escapeText(heading) +
    "</strong></summary>" +
    '<div class="truenas-ingress-detail">' +
    details.map((detail) => `<span>${escapeText(detail)}</span>`).join("") +
    "</div>";
}

export function decorateCloudflareTunnelStatuses(
  data,
  platformCheck = null,
  exposureSummary = null,
) {
  const checks = data?.checks || {};
  // api-sickz.js renders from the same snapshot. Defer one task so its rows exist.
  window.setTimeout(() => {
    Object.values(checks).forEach((check) => {
      const row = findRow(check);
      replaceDirectProbeWording(row, check);
      appendTunnelBadge(row, normalizeTunnelStatus(check), check);
    });
    renderTunnelStatus(checks, platformCheck, exposureSummary);
  }, 0);
}
