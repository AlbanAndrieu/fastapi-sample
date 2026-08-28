import {
  escapeText,
  lockHtml,
  shortHostForDetail,
  sickzRowIcon,
  tunnelHref,
} from "./api-health-ui.js";
import {
  hasReachableNon2xxHttp,
  isForbiddenOnlyReachable,
  networkPhrase,
  tcpPolicyViolation,
} from "./api-sickz-policy.js";
import { renderPfsenseSection } from "./api-sickz-pfsense.js";
import { organizeSickzRows } from "./api-service-groups.js";

function classifySick(check) {
  if (check.policy_status === "ok") return "green";
  if (check.policy_status === "warn") return "yellow";
  if (check.policy_status === "fail") return "red";
  if (check.policy_status === "unknown") return "gray";
  if (check.skipped === true) return "yellow";
  if (check.reachable === true) {
    if (isForbiddenOnlyReachable(check)) return "yellow";
    if (hasReachableNon2xxHttp(check)) return "blue";
    return "red";
  }
  if (check.reachable === false) return "green";
  return "gray";
}

function rawDetailSickText(check) {
  if (check.skipped === true) {
    const intro = check.reason || "Not probed (LAN skip).";
    if (check.aliases_probed && check.aliases_probed.length) {
      return `${intro} Targets: ${check.aliases_probed.map(shortHostForDetail).join(" · ")}`;
    }
    return intro;
  }
  if (check.alias_results && check.aliases_probed) {
    const bits = [];
    check.aliases_probed.forEach((url) => {
      const result = check.alias_results[url];
      const tail = shortHostForDetail(url);
      if (!result) return;
      if (result.reachable === true) {
        bits.push(
          `${tail} → reachable${result.http_status != null ? ` (HTTP ${result.http_status})` : ""}`,
        );
      } else if (result.error) {
        bits.push(`${tail} → unreachable (${result.error})`);
      } else {
        bits.push(`${tail} → unreachable`);
      }
    });
    const line = bits.join(" · ");
    if (isForbiddenOnlyReachable(check)) {
      return `${line} — HTTP 403 only: host responded but access is forbidden.`;
    }
    return line;
  }
  if (check.reachable === true) {
    const parts = ["Reachable."];
    if (check.http_status != null) parts.push(`HTTP ${check.http_status}`);
    return parts.join(" ");
  }
  if (check.reachable === false) {
    if (check.error) return `Unreachable. ${check.error}`;
    return "Unreachable.";
  }
  return "Unknown reachability state.";
}

function detailSickText(check) {
  const raw = rawDetailSickText(check);
  if (!check.policy_detail) return raw;
  const warning =
    check.policy_status === "warn" && !String(check.policy_detail).startsWith("⚠️")
      ? "⚠️ "
      : "";
  return `${raw} — ${warning}${check.policy_detail}`;
}

function computeOverall(data) {
  const network = networkPhrase(data);
  if (data.status === "skipped_internal_network") {
    return {
      cls: "yellow",
      text: `${data.detail || "Sickz skipped on internal network."} Network: ${network}.`,
    };
  }
  if (data.status === "no_targets" || Object.keys(data.checks || {}).length === 0) {
    return {
      cls: "yellow",
      text: `${data.detail || "No sickz targets configured."} Network: ${network}.`,
    };
  }

  const checks = data.checks || {};
  let anyPolicyFail = false;
  let anyPolicyWarn = false;
  let anyTcpPolicyViolation = false;
  let anyOpenReach2xx = false;
  let anyOpenReachNon2xx = false;
  let anyForbiddenOnly = false;
  for (const key of Object.keys(checks)) {
    const check = checks[key];
    if (check.skipped === true) continue;
    if (check.policy_status === "fail") {
      anyPolicyFail = true;
      continue;
    }
    if (check.policy_status === "warn") {
      anyPolicyWarn = true;
      continue;
    }
    if (check.policy_status === "ok") continue;
    if (tcpPolicyViolation(check)) anyTcpPolicyViolation = true;
    if (check.reachable === true) {
      if (isForbiddenOnlyReachable(check)) anyForbiddenOnly = true;
      else if (hasReachableNon2xxHttp(check)) anyOpenReachNon2xx = true;
      else anyOpenReach2xx = true;
    }
  }
  if (anyPolicyFail) {
    return {
      cls: "red",
      text: `From network ${network}, at least one service violates its declared exposure/Cloudflare policy.`,
    };
  }
  if (anyTcpPolicyViolation) {
    return {
      cls: "red",
      text: `From network ${network}, at least one TCP service violates its exposure policy; see the pfSense port checks.`,
    };
  }
  if (anyOpenReach2xx) {
    return {
      cls: "red",
      text: `From network ${network}, at least one unclassified target is reachable with HTTP 2xx.`,
    };
  }
  if (anyOpenReachNon2xx) {
    return {
      cls: "blue",
      text: `From network ${network}, at least one unclassified target responded with a non-2xx HTTP status; see rows.`,
    };
  }
  if (anyPolicyWarn) {
    return {
      cls: "yellow",
      text: `From network ${network}, exposure policy is compliant only with explicit security warnings; see orange rows.`,
    };
  }
  if (anyForbiddenOnly) {
    return {
      cls: "yellow",
      text: `From network ${network}, at least one target responded with HTTP 403 (Forbidden) only.`,
    };
  }
  return {
    cls: "green",
    text: `From network ${network}, all listed targets satisfy the configured exposure policy.`,
  };
}

function exposureTags(check) {
  if (!check.policy_status) {
    return check.alias_results
      ? "Equivalent URLs (any alias reachable fails the legacy check)"
      : "Legacy inverse-reachability target";
  }
  const external = check.external === true ? "external=true" : "external=false";
  const tunnel =
    check.tunnel_secure === true
      ? "Cloudflare expected"
      : check.tunnel_secure === false
        ? "direct exposure / no Cloudflare"
        : "security mode unspecified";
  const observed =
    check.cloudflare_tunnel_observed === true ? "Cloudflare observed" : "Cloudflare not observed";
  return `${external} · ${tunnel} · ${observed}`;
}

function render(data) {
  const listEl = document.getElementById("sickz-checks");
  const summaryEl = document.getElementById("sickz-summary");
  const summaryText = document.getElementById("sickz-summary-text");
  const summaryLed = document.getElementById("sickz-summary-led");
  const errEl = document.getElementById("sickz-fetch-error");

  errEl.hidden = true;
  errEl.textContent = "";

  const overall = computeOverall(data);
  summaryEl.className = `health-summary health-summary--${overall.cls}`;
  summaryLed.className = `health-led health-led--${overall.cls}`;
  summaryText.textContent = overall.text;

  const hintEl = document.getElementById("sickz-lan-hint");
  const runtime = data.runtime || {};
  if (hintEl) {
    if (data.status === "skipped_internal_network") {
      hintEl.hidden = false;
      if (runtime.sickz_internal_network_implicit) {
        hintEl.textContent = `LAN skip was inferred from ${runtime.internal_network_inferred_from || "SICKZ_NETWORK_LABEL / APP_DOMAIN rules"} (SICKZ_INTERNAL_NETWORK was not required).`;
      } else {
        hintEl.textContent = "LAN skip from SICKZ_INTERNAL_NETWORK=true.";
      }
    } else if (runtime.cloud_paas_detected) {
      hintEl.hidden = false;
      hintEl.textContent =
        "Cloud/PaaS runtime: sickz compares declared external/Cloudflare policy with HTTP, TLS and read-only Cloudflare Tunnel evidence.";
    } else {
      hintEl.hidden = true;
      hintEl.textContent = "";
    }
  }

  const checks = data.checks || {};
  const pfKey = renderPfsenseSection(checks, classifySick, detailSickText);
  const keys = Object.keys(checks).filter((key) => key !== pfKey).sort();
  listEl.innerHTML = "";

  keys.forEach((key) => {
    const check = checks[key];
    const cls = classifySick(check);
    const item = document.createElement("li");
    item.className = "health-row";
    item.dataset.serviceFilterTarget = "";
    item.dataset.serviceKey = key;
    const hrefRaw = tunnelHref(check);
    const safeHref = hrefRaw.length ? escapeText(hrefRaw) : "";
    let rowTitle = "";
    if (check.name != null && String(check.name).trim()) rowTitle = String(check.name).trim();
    else if (check.display_label != null) rowTitle = String(check.display_label);
    else rowTitle = key;
    if (check.policy_status === "warn") rowTitle = `⚠️ ${rowTitle}`;
    item.dataset.serviceName = rowTitle.replace(/^⚠️\s*/, "");
    item.dataset.serviceUrl = hrefRaw;
    item.dataset.searchText = [
      key,
      item.dataset.serviceName,
      hrefRaw,
      detailSickText(check),
      exposureTags(check),
    ]
      .join(" ")
      .toLowerCase();
    const lockTls = check.skipped === true ? null : check.tls_trusted;
    const lockHref = check.skipped === true ? "" : hrefRaw;
    const titleInner = safeHref
      ? `<a class="sickz-target-link" target="_blank" rel="noopener noreferrer" href="${safeHref}">${escapeText(rowTitle)}</a>`
      : `<span>${escapeText(rowTitle)}</span>`;
    item.innerHTML =
      sickzRowIcon(check, cls) +
      `<span class="health-row-led-wrap"><span class="health-led health-led--${cls}" title="${cls}"></span></span>` +
      '<div class="health-row-main">' +
      `<div class="health-row-primary health-row-primary--${cls}">` +
      '<div class="health-row-name health-row-name--sickz">' +
      lockHtml(lockTls, lockHref) +
      titleInner +
      "</div>" +
      `<div class="health-row-detail">${escapeText(detailSickText(check))}</div></div>` +
      `<div class="health-row-tags">${escapeText(exposureTags(check))}</div>` +
      "</div>";
    listEl.appendChild(item);
  });
  organizeSickzRows(data, pfKey);
}

function showFetchError(message) {
  const summaryEl = document.getElementById("sickz-summary");
  const summaryText = document.getElementById("sickz-summary-text");
  const summaryLed = document.getElementById("sickz-summary-led");
  const errEl = document.getElementById("sickz-fetch-error");
  const wrapPf = document.getElementById("sickz-pfsense-wrap");
  if (wrapPf) {
    wrapPf.hidden = true;
    wrapPf.innerHTML = "";
  }
  document.getElementById("sickz-checks").innerHTML = "";
  summaryEl.className = "health-summary health-summary--red";
  summaryLed.className = "health-led health-led--red";
  summaryText.textContent = "Could not load /sickz.";
  errEl.hidden = false;
  errEl.textContent = message;
}

export function loadSickz() {
  fetch("/sickz", { headers: { Accept: "application/json" } })
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then(render)
    .catch((error) => {
      showFetchError(String(error.message || error));
    });
}
