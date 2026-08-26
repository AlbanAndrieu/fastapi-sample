import {
  escapeText,
  httpStatusIsSuccess2xx,
  lockHtml,
  shortHostForDetail,
  sickzRowIcon,
  tunnelHref,
} from "./api-health-ui.js";
import {
  buildPfsenseSectionHtml,
  findPfsenseEntry,
} from "./api-sickz-pfsense.js";

function reachableHttpStatuses(check) {
  if (check.alias_results && check.aliases_probed) {
    const out = [];
    check.aliases_probed.forEach((url) => {
      const result = check.alias_results[url];
      if (result && result.reachable === true && result.http_status != null) {
        out.push(result.http_status);
      }
    });
    return out;
  }
  if (check.reachable === true && check.http_status != null) return [check.http_status];
  return [];
}

function isForbiddenOnlyReachable(check) {
  if (check.skipped === true || check.reachable !== true) return false;
  const statuses = reachableHttpStatuses(check);
  return statuses.length > 0 && statuses.every((status) => status === 403);
}

function hasReachableNon2xxHttp(check) {
  if (check.skipped === true || check.reachable !== true) return false;
  if (isForbiddenOnlyReachable(check)) return false;
  const statuses = reachableHttpStatuses(check);
  return statuses.some((status) => !httpStatusIsSuccess2xx(status));
}

function expectsReachable(check) {
  return check.expected_reachable === true;
}

function classifySick(check) {
  if (check.skipped === true) return "yellow";
  if (expectsReachable(check)) {
    if (check.reachable === true) return "green";
    if (check.reachable === false) return "red";
    return "gray";
  }
  if (check.reachable === true) {
    if (isForbiddenOnlyReachable(check)) return "yellow";
    if (hasReachableNon2xxHttp(check)) return "blue";
    return "red";
  }
  if (check.reachable === false) return "green";
  return "gray";
}

function detailSickText(check) {
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
      } else if (result.error) bits.push(`${tail} → unreachable (${result.error})`);
      else bits.push(`${tail} → unreachable`);
    });
    const line = bits.join(" · ");
    if (expectsReachable(check)) {
      return `${line} — direct WAN management endpoint: reachable is expected.`;
    }
    if (isForbiddenOnlyReachable(check)) {
      return `${line} — HTTP 403 only: host responded but access is forbidden (yellow, not full exposure).`;
    }
    return line;
  }
  if (check.reachable === true) {
    if (expectsReachable(check)) return "Reachable as expected.";
    const parts = ["Reachable (should be blocked)."];
    if (check.http_status != null) parts.push(`HTTP ${check.http_status}`);
    if (isForbiddenOnlyReachable(check)) {
      parts.push("HTTP 403: host reached but forbidden — shown as yellow.");
    }
    return parts.join(" ");
  }
  if (check.reachable === false) {
    if (expectsReachable(check)) {
      return check.error
        ? `Unreachable unexpectedly. ${check.error}`
        : "Unreachable unexpectedly.";
    }
    if (check.error) return `Unreachable as expected. ${check.error}`;
    return "Unreachable as expected.";
  }
  return "Unknown state.";
}

function networkPhrase(data) {
  return data.network_label ? `"${data.network_label}"` : "this deployment";
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

  let expectedReachabilityFailure = false;
  let tcpPolicyFailure = false;
  let openReach2xx = false;
  let openReachNon2xx = false;
  let forbiddenOnly = false;
  Object.values(data.checks || {}).forEach((check) => {
    if (check.skipped === true) return;
    if (check.pfsense_tcp_policy_failed === true) tcpPolicyFailure = true;
    if (expectsReachable(check)) {
      if (check.reachable !== true) expectedReachabilityFailure = true;
      return;
    }
    if (check.reachable !== true) return;
    if (isForbiddenOnlyReachable(check)) forbiddenOnly = true;
    else if (hasReachableNon2xxHttp(check)) openReachNon2xx = true;
    else openReach2xx = true;
  });

  if (expectedReachabilityFailure) {
    return {
      cls: "red",
      text: `From network ${network}, an endpoint that should be reachable is unavailable; see rows.`,
    };
  }
  if (tcpPolicyFailure) {
    return {
      cls: "red",
      text: `From network ${network}, at least one reviewed WAN TCP port differs from its expected exposure policy.`,
    };
  }
  if (openReach2xx) {
    return {
      cls: "red",
      text: `From network ${network}, at least one target is reachable with HTTP 2xx; it should stay blocked from this context.`,
    };
  }
  if (openReachNon2xx) {
    return {
      cls: "blue",
      text: `From network ${network}, at least one target responded but with a non-2xx HTTP status; see rows.`,
    };
  }
  if (forbiddenOnly) {
    return {
      cls: "yellow",
      text: `From network ${network}, at least one target responded with HTTP 403 only — reachable, but access denied.`,
    };
  }
  return {
    cls: "green",
    text: `From network ${network}, reviewed exposure policies match their expected state.`,
  };
}

function renderLanHint(data) {
  const hintEl = document.getElementById("sickz-lan-hint");
  if (!hintEl) return;
  const runtime = data.runtime || {};
  if (data.status === "skipped_internal_network") {
    hintEl.hidden = false;
    hintEl.textContent = runtime.sickz_internal_network_implicit
      ? `LAN skip was inferred from ${runtime.internal_network_inferred_from || "SICKZ_NETWORK_LABEL / APP_DOMAIN rules"}.`
      : "LAN skip from SICKZ_INTERNAL_NETWORK=true.";
    return;
  }
  if (
    runtime.cloud_paas_detected &&
    (runtime.sickz_internal_network_config || runtime.sickz_internal_network_implicit)
  ) {
    hintEl.hidden = false;
    hintEl.textContent =
      "Cloud/PaaS runtime: sickz probes still run even though home-LAN rules would otherwise match.";
    return;
  }
  hintEl.hidden = true;
  hintEl.textContent = "";
}

function renderCheckRow(key, check) {
  const cls = classifySick(check);
  const item = document.createElement("li");
  item.className = "health-row";
  const hrefRaw = tunnelHref(check);
  const safeHref = hrefRaw.length ? escapeText(hrefRaw) : "";
  const rowTitle =
    check.name != null && String(check.name).trim()
      ? String(check.name).trim()
      : check.display_label != null
        ? String(check.display_label)
        : key;
  const lockTls = check.skipped === true ? null : check.tls_trusted;
  const lockHref = check.skipped === true ? "" : hrefRaw;
  const titleInner = safeHref.length
    ? `<a class="sickz-target-link" target="_blank" rel="noopener noreferrer" href="${safeHref}">${escapeText(rowTitle)}</a>`
    : `<span>${escapeText(rowTitle)}</span>`;
  const tags = check.skipped
    ? "Listed for reference; not probed on this network"
    : expectsReachable(check)
      ? "Expected to be reachable"
      : check.alias_results
        ? "Equivalent URLs (any alias reachable fails the check)"
        : "Must not be reachable";

  item.innerHTML =
    sickzRowIcon(check, cls) +
    `<span class="health-row-led-wrap"><span class="health-led health-led--${cls}" title="${cls}"></span></span>` +
    '<div class="health-row-main">' +
    `<div class="health-row-primary health-row-primary--${cls}">` +
    '<div class="health-row-name health-row-name--sickz">' +
    lockHtml(lockTls, lockHref) +
    titleInner +
    "</div>" +
    `<div class="health-row-detail">${detailSickText(check)}</div></div>` +
    `<div class="health-row-tags">${tags}</div></div>`;
  return item;
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
  renderLanHint(data);

  const checks = data.checks || {};
  const pfEntry = findPfsenseEntry(checks);
  const pfKey = pfEntry ? pfEntry.key : null;
  const wrapPf = document.getElementById("sickz-pfsense-wrap");
  if (wrapPf) {
    wrapPf.hidden = !pfEntry;
    wrapPf.innerHTML = pfEntry
      ? buildPfsenseSectionHtml(pfEntry.check, classifySick, detailSickText)
      : "";
  }

  listEl.innerHTML = "";
  Object.keys(checks)
    .filter((key) => key !== pfKey)
    .sort()
    .forEach((key) => listEl.appendChild(renderCheckRow(key, checks[key])));
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
    .catch((error) => showFetchError(String(error.message || error)));
}
