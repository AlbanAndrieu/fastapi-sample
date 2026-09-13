export const PROBE_COLUMNS = [
  ["dns", "🧭", "DNS"],
  ["http", "🌐", "HTTP"],
  ["tls", "🔒", "TLS"],
  ["cloudflare", "☁️", "Tunnel"],
  ["access", "🛡️", "Access"],
  ["service-token", "🔑", "Token"],
  ["api", "⚙️", "API"],
  ["policy", "🛡️", "Policy"],
  ["tcp", "🔌", "TCP"],
  ["websocket", "↔", "WebSocket"],
  ["metrics", "📈", "Prometheus"],
];

const ROW_SELECTOR = "[data-service-filter-target]";
let scheduled = false;

function probeTone(probe) {
  if (!probe || probe.dataset.probePlaceholder === "true") return "neutral";
  if (probe.dataset.probeDisabled === "true") return "neutral";
  const tone = [...probe.classList]
    .find((name) => name.startsWith("service-probe--"))
    ?.replace("service-probe--", "");
  return ["ok", "warn", "fail", "unknown", "neutral"].includes(tone)
    ? tone
    : "unknown";
}

function sourceProbes(row) {
  const byKind = new Map();
  for (const probe of row.querySelectorAll(
    ".service-probe[data-probe-kind]:not([data-probe-grid-copy])",
  )) {
    const kind = String(probe.dataset.probeKind || "").trim();
    if (!kind) continue;
    const current = byKind.get(kind);
    const currentWeak =
      !current ||
      current.dataset.probePlaceholder === "true" ||
      current.dataset.probeDisabled === "true";
    const candidateStrong =
      probe.dataset.probePlaceholder !== "true" &&
      probe.dataset.probeDisabled !== "true";
    if (!current || (currentWeak && candidateStrong)) byKind.set(kind, probe);
  }
  return byKind;
}

function probeDetail(probe, label) {
  if (!probe) {
    return `${label} probe evidence is not available in the current snapshot.`;
  }
  return (
    probe.getAttribute("aria-label") ||
    probe.title ||
    `${label} probe evidence is available.`
  );
}

function probeHref(probe) {
  if (!(probe instanceof HTMLAnchorElement)) return "";
  try {
    const url = new URL(probe.href, window.location.href);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

function probeSignature(byKind) {
  return JSON.stringify(
    PROBE_COLUMNS.map(([kind, , label]) => {
      const probe = byKind.get(kind);
      return [
        kind,
        probeTone(probe),
        probeDetail(probe, label),
        probeHref(probe),
      ];
    }),
  );
}

function pinColumn(cell, columnIndex) {
  const column = columnIndex + 1;
  cell.dataset.probeColumn = String(column);
  cell.style.gridColumn = String(column);
  cell.setAttribute("role", "cell");
}

function makeCardCell(kind, icon, label, source, columnIndex) {
  const tone = probeTone(source);
  const cell = document.createElement("div");
  cell.className = `service-probe-table-cell service-probe-table-cell--${tone}`;
  cell.dataset.probeKind = kind;
  cell.dataset.probeGridCopy = "true";
  cell.title = probeDetail(source, label);
  cell.setAttribute("aria-label", cell.title);
  pinColumn(cell, columnIndex);

  const iconNode = document.createElement("span");
  iconNode.className = "service-probe-table-icon";
  iconNode.setAttribute("aria-hidden", "true");
  iconNode.textContent = icon;

  const labelNode = document.createElement("span");
  labelNode.className = "service-probe-table-label";
  labelNode.textContent = label;

  cell.append(iconNode, labelNode);
  return cell;
}

function renderCardGrid(row) {
  const primary = row.querySelector(":scope .health-row-primary");
  if (!primary) return;
  const sources = sourceProbes(row);
  const signature = probeSignature(sources);
  let grid = primary.querySelector(":scope > .service-probe-table");
  if (!grid) {
    grid = document.createElement("div");
    grid.className = "service-probe-table";
    grid.dataset.probeGrid = "card";
    grid.setAttribute("role", "table");
    grid.setAttribute("aria-label", "Stable probe evidence");
    grid.setAttribute("aria-colcount", String(PROBE_COLUMNS.length));
    primary.appendChild(grid);
  }
  if (grid.dataset.signature === signature) {
    row.dataset.probeGridReady = "true";
    return;
  }

  const fragment = document.createDocumentFragment();
  for (const [columnIndex, [kind, icon, label]] of PROBE_COLUMNS.entries()) {
    fragment.appendChild(
      makeCardCell(kind, icon, label, sources.get(kind), columnIndex),
    );
  }
  grid.replaceChildren(fragment);
  grid.dataset.signature = signature;
  row.dataset.probeGridReady = "true";
}

function makeDrawerCell(kind, icon, label, source, columnIndex) {
  const tone = probeTone(source);
  const item = document.createElement("article");
  item.className = `service-detail-probe service-detail-probe--${tone}`;
  item.dataset.probeKind = kind;
  item.dataset.probeGridCopy = "true";
  pinColumn(item, columnIndex);

  const heading = document.createElement("div");
  heading.className = "service-detail-probe-heading";
  const name = document.createElement("span");
  name.className = "service-detail-probe-name";
  const iconNode = document.createElement("span");
  iconNode.className = "service-detail-probe-icon";
  iconNode.dataset.tone = tone;
  iconNode.setAttribute("aria-hidden", "true");
  iconNode.textContent = icon;

  const href = probeHref(source);
  const labelNode = document.createElement(href ? "a" : "strong");
  labelNode.className = "service-detail-probe-label";
  labelNode.textContent = label;
  if (labelNode instanceof HTMLAnchorElement) {
    labelNode.href = href;
    labelNode.target = "_blank";
    labelNode.rel = "noopener noreferrer";
  }
  name.append(iconNode, labelNode);
  heading.appendChild(name);

  const detail = document.createElement("p");
  detail.textContent = probeDetail(source, label);
  item.append(heading, detail);
  return item;
}

function renderDrawerGrid() {
  const row = document.querySelector(
    `${ROW_SELECTOR}[data-detail-selected="true"]`,
  );
  const host = document.getElementById("service-detail-evidence");
  if (!row || !host) return;
  const sources = sourceProbes(row);
  const signature = probeSignature(sources);
  if (
    host.dataset.probeGridReady === "true" &&
    host.dataset.signature === signature
  ) {
    return;
  }

  const fragment = document.createDocumentFragment();
  for (const [columnIndex, [kind, icon, label]] of PROBE_COLUMNS.entries()) {
    fragment.appendChild(
      makeDrawerCell(kind, icon, label, sources.get(kind), columnIndex),
    );
  }
  host.replaceChildren(fragment);
  host.dataset.probeGridReady = "true";
  host.dataset.signature = signature;
  host.setAttribute("role", "table");
  host.setAttribute("aria-label", "Stable probe evidence details");
  host.setAttribute("aria-colcount", String(PROBE_COLUMNS.length));
}

function render() {
  scheduled = false;
  for (const row of document.querySelectorAll(ROW_SELECTOR))
    renderCardGrid(row);
  renderDrawerGrid();
}

function schedule() {
  if (scheduled) return;
  scheduled = true;
  window.requestAnimationFrame(render);
}

function observe() {
  const board = document.getElementById("health-board");
  if (board) {
    new MutationObserver(schedule).observe(board, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["class", "data-probe-kind", "data-probe-disabled"],
    });
  }
  const drawer = document.getElementById("service-detail-drawer");
  if (drawer) {
    new MutationObserver(schedule).observe(drawer, {
      childList: true,
      subtree: true,
    });
  }
}

export function installHealthUiProbeGrid() {
  observe();
  document.addEventListener("health-board-refreshed", schedule);
  document.addEventListener("service-filter-changed", schedule);
  document.addEventListener("click", (event) => {
    if (
      event.target instanceof Element &&
      event.target.closest(".service-detail-trigger")
    ) {
      window.setTimeout(schedule, 0);
    }
  });
  schedule();
}
