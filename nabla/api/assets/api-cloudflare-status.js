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

function controlPlaneConfirmed(platformCheck) {
  return (
    platformCheck?.api_reachable === true &&
    platformCheck?.status_confirmed === true
  );
}

function normalizeTunnelStatus(check, platformCheck) {
  if (check.tunnel_secure !== true) return null;

  if (!controlPlaneConfirmed(platformCheck)) {
    const reason = String(
      platformCheck?.error ||
        platformCheck?.warning ||
        "Cloudflare API control-plane evidence is not confirmed",
    ).trim();
    return {
      cls: "gray",
      label: "Cloudflare verification unavailable",
      detail: `Tunnel/API-derived policy controls are disabled until the read-only Cloudflare API is confirmed. ${reason}`,
      disabled: true,
    };
  }

  const observed = check.cloudflare_tunnel_observed;
  const status = String(check.cloudflare_tunnel_status || "").toUpperCase();
  if (
    observed === true &&
    (!status || ["HEALTHY", "ACTIVE", "UP"].includes(status))
  ) {
    return {
      cls: "green",
      label: "Cloudflare route confirmed",
      detail: status
        ? `Tunnel route observed (${status}).`
        : "Tunnel route hostname observed.",
    };
  }

  if (observed === true) {
    return {
      cls: "yellow",
      label: "Cloudflare route needs attention",
      detail: `Tunnel route exists but its Tunnel reports ${status || "an uncertain state"}.`,
    };
  }

  const edgeObserved =
    check.cloudflare_http_evidence === true ||
    check.cloudflare_edge_observed === true ||
    check.cloudflare_edge_headers_observed === true;
  if (edgeObserved) {
    return {
      cls: "yellow",
      label: "Cloudflare route mismatch",
      detail:
        "Cloudflare edge traffic is observed, but this hostname is not confirmed in the current Tunnel Public Hostname inventory.",
    };
  }

  return {
    cls: "red",
    label: "Cloudflare route missing",
    detail:
      "Cloudflare API inventory is confirmed, but this declared protected hostname has no matching Tunnel Public Hostname route.",
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
  const appCount = Number(check.cloudflare_access_application_count);

  if (Number.isFinite(appCount)) {
    parts.push(`${appCount} Access app${appCount === 1 ? "" : "s"}`);
  }
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
      `Service Token ${tokenOutcome}${Number.isFinite(tokenStatus) ? ` (HTTP ${tokenStatus})` : ""}`,
    );
  }
  return parts.join(" · ");
}

function controlPlaneDetail(exposureSummary) {
  const control = exposureSummary?.control_plane || {};
  const labels = [
    ["Tunnels", control.tunnels],
    ["Access apps", control.access_applications],
    ["Reusable policies", control.access_reusable_policies],
    ["Service Tokens", control.access_service_tokens],
  ];
  const parts = [];
  for (const [label, family] of labels) {
    if (!family) continue;
    const count = Number(family.total_count ?? family.result_count);
    const elapsed = Number(family.elapsed_ms);
    const bits = [label];
    if (Number.isFinite(count)) bits.push(`count=${count}`);
    if (Number.isFinite(elapsed)) bits.push(`${elapsed}ms`);
    if (family.success === false)
      bits.push(`error=${family.error || "unknown"}`);
    parts.push(bits.join(" "));
  }
  return parts.join(" · ");
}

function hostnameOf(value) {
  try {
    return new URL(String(value || ""), window.location.href).hostname
      .toLowerCase()
      .replace(/\.$/, "");
  } catch {
    return "";
  }
}

function routeDetail(check, exposureSummary) {
  const hostname = hostnameOf(
    check.tunnel_url || check.tunnelUrl || check.href || "",
  );
  if (!hostname) return "";
  for (const tunnel of exposureSummary?.tunnels || []) {
    const route = (tunnel?.ingress || []).find(
      (candidate) =>
        String(candidate?.hostname || "").toLowerCase() === hostname,
    );
    if (!route) continue;
    return [
      `${hostname} → ${route.service || "origin unknown"}`,
      `Tunnel ${tunnel.name || "unknown"}`,
      `status=${tunnel.status || "unknown"}`,
    ].join(" · ");
  }
  if (check.cloudflare_origin_service) {
    return `${hostname} → ${check.cloudflare_origin_service}`;
  }
  return "";
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

function appendTunnelBadge(row, state, check, exposureSummary) {
  if (!row || !state || row.querySelector(".cloudflare-tunnel-badge")) return;
  const tags =
    row.querySelector(".health-row-tags") ||
    row.querySelector(".health-row-main");
  if (!tags) return;
  const badge = document.createElement("span");
  badge.className = `cloudflare-tunnel-badge cloudflare-tunnel-badge--${state.cls}`;
  if (state.disabled) {
    badge.dataset.probeDisabled = "true";
    badge.setAttribute("aria-disabled", "true");
  }
  const hover = [
    state.label,
    state.detail,
    routeDetail(check, exposureSummary),
    state.disabled ? "" : cloudflarePolicyDetail(check),
    controlPlaneDetail(exposureSummary),
  ]
    .filter(Boolean)
    .join(" · ");
  badge.title = hover;
  badge.setAttribute("role", "img");
  badge.setAttribute("aria-label", hover);
  badge.innerHTML = `<img src="${CLOUDFLARE_ICON}" alt="" width="18" height="18" loading="lazy"> <span>Cloudflare</span>`;
  tags.appendChild(badge);
}

function retireLegacyTunnelStatusBlock() {
  const container = document.getElementById("cloudflare-tunnel-warning");
  if (!container) return;
  container.hidden = true;
  container.open = false;
  container.replaceChildren();
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
      appendTunnelBadge(
        row,
        normalizeTunnelStatus(check, platformCheck),
        check,
        exposureSummary,
      );
    });
    retireLegacyTunnelStatusBlock();
  }, 0);
}
