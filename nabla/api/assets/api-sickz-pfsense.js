import {
  escapeText,
  lockHtml,
  sickzRowIcon,
  tunnelHref,
} from "./api-health-ui.js";

export function findPfsenseEntry(checks) {
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

function tcpPortNumbers(map) {
  if (!map || typeof map !== "object") return [];
  return Object.keys(map)
    .map((value) => Number.parseInt(value, 10))
    .filter((value) => !Number.isNaN(value))
    .sort((left, right) => left - right);
}

function portChipClass(reachable, expected) {
  if (reachable == null || typeof expected !== "boolean") {
    return "sickz-pfsense-port--na";
  }
  return reachable === expected
    ? "sickz-pfsense-port--closed"
    : "sickz-pfsense-port--open";
}

function portLabel(reachable, expected) {
  if (reachable == null) return "not probed";
  const state = reachable === true ? "reachable" : "unreachable";
  if (typeof expected !== "boolean") return state;
  return `${state} · ${reachable === expected ? "expected" : "unexpected"}`;
}

export function buildPfsenseSectionHtml(pfCheck, classifySick, detailSickText) {
  const cls = classifySick(pfCheck);
  const hrefRaw = tunnelHref(pfCheck);
  const safeHref = hrefRaw.length ? escapeText(hrefRaw) : "";
  const lockTls = pfCheck.skipped === true ? null : pfCheck.tls_trusted;
  const lockHref = pfCheck.skipped === true ? "" : hrefRaw;
  const portsMap = pfCheck.pfsense_tcp_ports;
  const expectations = pfCheck.pfsense_tcp_port_expectations || {};
  const labels = pfCheck.pfsense_tcp_port_labels || {};
  let chips = "";
  tcpPortNumbers(portsMap).forEach((port) => {
    const key = String(port);
    const reachable = portsMap[key];
    const expected = expectations[key];
    const label = portLabel(reachable, expected);
    const serviceLabel = labels[key] ? ` · ${labels[key]}` : "";
    chips +=
      `<span class="sickz-pfsense-port ${portChipClass(reachable, expected)}" ` +
      `title="TCP ${port}${serviceLabel}: ${label}">` +
      `<span class="sickz-pfsense-port-num">${port}</span>` +
      `<span class="sickz-pfsense-port-st">${escapeText(label)}</span></span>`;
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
  const titleLink = safeHref.length
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
