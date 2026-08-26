import {
  escapeText,
  httpStatusIsSuccess2xx,
  lockHtml,
  shortHostForDetail,
  sickzRowIcon,
  tunnelHref,
} from "./api-health-ui.js";

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
  if (statuses.length === 0) return false;
  return statuses.every((status) => status === 403);
}

function hasReachableNon2xxHttp(check) {
  if (check.skipped === true || check.reachable !== true) return false;
  if (isForbiddenOnlyReachable(check)) return false;
  const statuses = reachableHttpStatuses(check);
  if (statuses.length === 0) return false;
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
      } else if (result.error) {
        bits.push(`${tail} → unreachable (${result.error})`);
      } else {
        bits.push(`${tail} → unreachable`);
      }
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

  const checks = data.checks || {};
  let anyExpectedReachabilityFailure = false;
  let anyTcpPolicyFailure = false;
  let anyOpenReach2xx = false;
  let anyOpenReachNon2xx = false;
  let anyForbiddenOnly = false;
  for (const key of Object.keys(checks)) {
    const check = checks[key];
    if (check.skipped === true) continue;
    if (check.pfsense_tcp_policy_failed === true) anyTcpPolicyFailure = true;
    if (expectsReachable(check)) {
      if (check.reachable !== true) anyExpectedReachabilityFailure = true;
      continue;
    }
    if (check.reachable === true) {
      if (isForbiddenOnlyReachable(check)) anyForbiddenOnly = true;
      else if (hasReachableNon2xxHttp(check)) anyOpenReachNon2xx = true;
      else anyOpenReach2xx = true;
    }
  }
  if (anyExpectedReachabilityFailure) {
    return {
      cls: "red",
      text: `From network ${network}, an endpoint that should be reachable is unavailable; see rows.`,
    };
  }
  if (anyTcpPolicyFailure) {
    return {
      cls: "red",
      text: `From network ${network}, at least one reviewed WAN TCP port differs from its expected exposure policy.`,
    };
  }
  if (anyOpenReach2xx) {
    return {
      cls: "red",
      text: `From network ${network}, at least one target is reachable with HTTP 2xx; it should stay blocked from this context.`,
    };
  }
  if (anyOpenReachNon2xx) {
    return {
      cls: "blue",
      text: `From network ${network}, at least one target responded but with a non-2xx HTTP status (e.g. 400, 502); see rows.`,
    };
  }
  if (anyForbiddenOnly) {
    return {
      cls: "yellow",
      text: `From network ${network}, at least one target responded with HTTP 403 (Forbidden) only — the host is reachable but access is denied.`,
    };
  }
  return {
    cls: "green",
    text: `From network ${network}, reviewed exposure policies match their expected state.`,
  };
}

function findPfsenseEntry(checks) {
  const keys = Object.keys(checks || {});
  for (const key of keys) {
    const check = checks[key];
    if (!check) continue;
    if (check.display_label === "PfSense" || check.name === "PfSense") {
      return { key, check };
    }
    if (check.pfsense_tcp_ports && typeof check.pfsense_tcp_ports === "object") {
      return { key, check };
    }
  }
  return null;
}

function pfsenseTcpPortNumbers(map) {
  if (!map || typeof map !== "object") return [];
  return Object.keys(map)
    .map((value) => Number.parseInt(value, 10))
    .filter((value) => !Number.isNaN(value))
    .sort((left, right) => left - right);
}

function pfsensePortChipClass(reachable, expected) {
  if (reachable == null) return "sickz-pfsense-port--na";
  if (typeof expected !== "boolean") return "sickz-pfsense-port--na";
  return reachable === expected ? "sickz-pfsense-port--closed" : "sickz-pfsense-port--open";
}

function pfsensePortLabel(reachable, expected) {
  if (reachable == null) return "not probed";
  const state = reachable === true ? "reachable" : "unreachable";
  if (typeof expected !== "boolean") return state;
  return `${state} · ${reachable === expected ? "expected" : "unexpected"}`;
}

function buildPfsenseSectionHtml(pfCheck) {
  const cls = classifySick(pfCheck);
  const hrefRaw = tunnelHref(pfCheck);
  const safeHref = hrefRaw.length ? escapeText(hrefRaw) : "";
  const lockTls = pfCheck.skipped === true ? null : pfCheck.tls_trusted;
  const lockHref = pfCheck.skipped === true ? "" : hrefRaw;
  const portsMap = pfCheck.pfsense_tcp_ports;
  const expectations = pfCheck.pfsense_tcp_port_expectations || {};
  const labels = pfCheck.pfsense_tcp_port_labels || {};
  const nums = pfsenseTcpPortNumbers(portsMap);
  let chips = "";
  nums.forEach((port) => {
    const key = String(port);
    const reachable = portsMap[key];
    const expected = expectations[key];
    const portClass = pfsensePortChipClass(reachable, expected);
    const portLabel = pfsensePortLabel(reachable, expected);
    const serviceLabel = labels[key] ? ` · ${labels[key]}` : "";
    chips +=
      `<span class="sickz-pfsense-port ${portClass}" title="TCP ${port}${serviceLabel}: ${portLabel}">` +
      `<span class="sickz-pfsense-port-num">${port}</span>` +
      `<span class="sickz-pfsense-port-st">${escapeText(portLabel)}</span></span>`;
  });
  let meta =
    "pfSense HTTPS on " +
    '<code class="sickz-pfsense-host">home.albandrieu.com:10443</code> is an explicitly allowed direct WAN management endpoint. ' +
    "The TCP chips below are external observations; only ports with a reviewed expectation are pass/fail checks.";
  if (pfCheck.pfsense_tcp_ports_skipped === true) {
    meta += " TCP probes were not run (LAN skip).";
  }
  const rowName =
    pfCheck.name != null && String(pfCheck.name).trim()
      ? String(pfCheck.name).trim()
      : String(pfCheck.display_label || "PfSense");
  const titleLink =
    safeHref.length > 0
      ? `<a class="sickz-target-link" target="_blank" rel="noopener noreferrer" href="${safeHref}">${escapeText(rowName)}</a>`
      : `<span>${escapeText(rowName)}</span>`;
  return (
    '<h4 class="sickz-pfsense-title">PfSense / WAN exposure</h4>' +
    `<p class="health-board-meta sickz-pfsense-intro">${meta}</p>` +
    '<ul class="health-checks sickz-pfsense-main"><li class="health-row sickz-pfsense-row">' +
    sickzRowIcon(pfCheck, cls) +
    `<span class="health-row-led-wrap"><span class="health-led health-led--${cls}" title="${cls}"></span></span>` +
    '<div class="health-row-main">' +
    `<div class="health-row-primary health-row-primary--${cls}">` +
    '<div class="health-row-name health-row-name--sickz">' +
    lockHtml(lockTls, lockHref) +
    titleLink +
    "</div>" +
    `<div class="health-row-detail">${escapeText(detailSickText(pfCheck))}</div></div>` +
    '<div class="health-row-tags">Direct WAN management · expected reachable</div>' +
    "</div></li></ul>" +
    '<div class="sickz-pfsense-ports-label">TCP exposure (home.albandrieu.com)</div>' +
    `<div class="sickz-pfsense-ports">${chips}</div>`
  );
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
    } else if (
      runtime.cloud_paas_detected &&
      (runtime.sickz_internal_network_config || runtime.sickz_internal_network_implicit)
    ) {
      hintEl.hidden = false;
      hintEl.textContent =
        "Cloud/PaaS runtime: sickz probes still run even though this host would match home-LAN rules (env or implicit label/domain).";
    } else {
      hintEl.hidden = true;
      hintEl.textContent = "";
    }
  }

  const checks = data.checks || {};
  const pfEntry = findPfsenseEntry(checks);
  const pfKey = pfEntry ? pfEntry.key : null;
  const wrapPf = document.getElementById("sickz-pfsense-wrap");
  if (wrapPf) {
    if (!pfEntry) {
      wrapPf.hidden = true;
      wrapPf.innerHTML = "";
    } else {
      wrapPf.hidden = false;
      wrapPf.innerHTML = buildPfsenseSectionHtml(pfEntry.check);
    }
  }

  const keys = Object.keys(checks)
    .filter((key) => key !== pfKey)
    .sort();
  listEl.innerHTML = "";

  keys.forEach((key) => {
    const check = checks[key];
    const cls = classifySick(check);
    const item = document.createElement("li");
    item.className = "health-row";
    const hrefRaw = tunnelHref(check);
    const safeHref = hrefRaw.length ? escapeText(hrefRaw) : "";
    let rowTitle = "";
    if (check.name != null && String(check.name).trim()) rowTitle = String(check.name).trim();
    else if (check.display_label != null) rowTitle = String(check.display_label);
    else rowTitle = key;
    const lockTls = check.skipped === true ? null : check.tls_trusted;
    const lockHref = check.skipped === true ? "" : hrefRaw;
    const titleInner =
      safeHref.length > 0
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
      `<div class="health-row-detail">${detailSickText(check)}</div></div>` +
      `<div class="health-row-tags">${
        check.skipped
          ? "Listed for reference; not probed on this network"
          : expectsReachable(check)
            ? "Expected to be reachable"
            : check.alias_results
              ? "Equivalent URLs (any alias reachable fails the check)"
              : "Must not be reachable"
      }</div>` +
      "</div>";
    listEl.appendChild(item);
  });
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
