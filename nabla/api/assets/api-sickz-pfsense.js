import { escapeText, lockHtml, sickzRowIcon, tunnelHref } from "./api-health-ui.js";

function findPfsenseEntry(checks) {
  for (const key of Object.keys(checks || {})) {
    const check = checks[key];
    if (!check) continue;
    if (check.display_label === "PfSense" || check.name === "PfSense") return { key, check };
    if (check.pfsense_tcp_ports && typeof check.pfsense_tcp_ports === "object") return { key, check };
  }
  return null;
}

function tcpPortNumbers(map) {
  if (!map || typeof map !== "object") return [];
  return Object.keys(map)
    .map((value) => Number.parseInt(value, 10))
    .filter((value) => !Number.isNaN(value))
    .sort((left, right) => left - right);
}

function portPolicy(check, port) {
  const map = check.pfsense_tcp_port_policy;
  if (!map || typeof map !== "object") return null;
  return map[String(port)] || null;
}

function portChipClass(reachable, policy) {
  if (reachable == null) return "sickz-pfsense-port--na";
  if (policy && typeof policy.expected_reachable === "boolean") {
    return reachable === policy.expected_reachable
      ? "sickz-pfsense-port--closed"
      : "sickz-pfsense-port--open";
  }
  return reachable ? "sickz-pfsense-port--open" : "sickz-pfsense-port--closed";
}

function portLabel(reachable, policy) {
  if (reachable == null) return "indeterminate";
  const state = reachable ? "reachable" : "blocked";
  if (!policy || typeof policy.expected_reachable !== "boolean") return state;
  return `${state} · ${reachable === policy.expected_reachable ? "expected" : "unexpected"}`;
}

function sectionHtml(check, classifySick, detailSickText) {
  const cls = classifySick(check);
  const hrefRaw = tunnelHref(check);
  const safeHref = hrefRaw.length ? escapeText(hrefRaw) : "";
  const lockTls = check.skipped === true ? null : check.tls_trusted;
  const lockHref = check.skipped === true ? "" : hrefRaw;
  const portsMap = check.pfsense_tcp_ports || {};
  const chips = tcpPortNumbers(portsMap)
    .map((port) => {
      const reachable = portsMap[String(port)];
      const policy = portPolicy(check, port);
      const label = portLabel(reachable, policy);
      const serviceLabel = policy?.service ? ` · ${policy.service}` : "";
      const expectedLabel =
        policy && typeof policy.expected_reachable === "boolean"
          ? ` · expected ${policy.expected_reachable ? "reachable" : "blocked"}`
          : "";
      return (
        `<span class="sickz-pfsense-port ${portChipClass(reachable, policy)}" ` +
        `title="TCP ${port}${serviceLabel}: ${label}${expectedLabel}">` +
        `<span class="sickz-pfsense-port-num">${port}</span>` +
        `<span class="sickz-pfsense-port-st">${escapeText(label)}</span></span>`
      );
    })
    .join("");

  let meta =
    "Known TCP services use protocol-aware checks; unknown ports are not trusted on cloud/PaaS from a TCP handshake alone. " +
    '<code class="sickz-pfsense-host">home.albandrieu.com</code> is the external probe host.';
  if (check.pfsense_tcp_ports_skipped === true) meta += " TCP probes were not run (LAN skip).";

  const rowName =
    check.name != null && String(check.name).trim()
      ? String(check.name).trim()
      : String(check.display_label || "PfSense");
  const titleLink = safeHref
    ? `<a class="sickz-target-link" target="_blank" rel="noopener noreferrer" href="${safeHref}">${escapeText(rowName)}</a>`
    : `<span>${escapeText(rowName)}</span>`;

  return (
    '<h4 class="sickz-pfsense-title">Critical core platform · pfSense public exposure policy</h4>' +
    `<p class="health-board-meta sickz-pfsense-intro">${meta}</p>` +
    '<ul class="health-checks sickz-pfsense-main"><li class="health-row sickz-pfsense-row">' +
    sickzRowIcon(check, cls) +
    `<span class="health-row-led-wrap"><span class="health-led health-led--${cls}" title="${cls}"></span></span>` +
    '<div class="health-row-main">' +
    `<div class="health-row-primary health-row-primary--${cls}">` +
    '<div class="health-row-name health-row-name--sickz">' +
    lockHtml(lockTls, lockHref) +
    titleLink +
    "</div>" +
    `<div class="health-row-detail">${escapeText(detailSickText(check))}</div></div>` +
    '<div class="health-row-tags">PfSense · HTTPS UI + policy-aware public TCP ports</div>' +
    "</div></li></ul>" +
    '<div class="sickz-pfsense-ports-label">TCP ports (home.albandrieu.com)</div>' +
    `<div class="sickz-pfsense-ports">${chips}</div>`
  );
}

export function renderPfsenseSection(checks, classifySick, detailSickText) {
  const entry = findPfsenseEntry(checks);
  const wrap = document.getElementById("sickz-pfsense-wrap");
  if (!wrap) return entry?.key || null;
  if (!entry) {
    wrap.hidden = true;
    wrap.innerHTML = "";
    return null;
  }
  wrap.hidden = false;
  wrap.dataset.serviceFilterTarget = "";
  wrap.dataset.searchText = `pfsense firewall critical core platform public port exposure security policy ${detailSickText(entry.check)}`.toLowerCase();
  wrap.innerHTML = sectionHtml(entry.check, classifySick, detailSickText);
  return entry.key;
}
