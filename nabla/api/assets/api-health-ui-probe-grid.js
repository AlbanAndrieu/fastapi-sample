export const PROBE_COLUMNS = [
  // Follow the request path. Columns report evidence, not assumptions.
  ["dns", "🧭", "DNS"],
  ["tcp", "🔌", "TCP"],
  ["tls", "🔒", "TLS"],
  ["http", "🌐", "HTTP"],
  ["cloudflare", "☁️", "Tunnel"],
  ["access", "🛡️", "Access"],
  ["service-token", "🔑", "Token"],
  ["api", "⚙️", "API"],
  ["websocket", "↔", "WebSocket"],
  ["metrics", "📈", "Metrics"],
  ["policy", "🛡️", "Policy"],
];

const ROW_SELECTOR = "[data-service-filter-target]";
let scheduled = false;

function probeTone(probe) {
  if (!probe || probe.dataset.probePlaceholder === "true") return "neutral";
  if (probe.dataset.probeDisabled === "true") return "neutral";
  const tone = [...probe.classList]
    .find((name) => name.startsWith("service-probe--"))
    ?.replace("service-probe--", "");
  // "info" is an expected auth challenge: both render as expected (blue).
  if (tone === "info") return "expected";
  return ["ok", "warn", "fail", "unknown", "neutral", "expected"].includes(tone)
    ? tone
    : "unknown";
}

function probeStateLabel(probe) {
  if (!probe || probe.dataset.probePlaceholder === "true") {
    return "Not sampled";
  }
  if (probe.dataset.probeDisabled === "true") return "Disabled";
  return {
    ok: "Pass",
    warn: "Warning",
    fail: "Failed",
    unknown: "Unknown",
    neutral: "Unconfirmed",
    expected: "Expected",
  }[probeTone(probe)];
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

// Hover details (ages, latency) change on every refresh; they are updated in
// place by refreshDetails so the cells are rebuilt only when a state changes.
function probeSignature(byKind) {
  return JSON.stringify(
    PROBE_COLUMNS.map(([kind]) => {
      const probe = byKind.get(kind);
      return [kind, probeTone(probe), probeStateLabel(probe), probeHref(probe)];
    }),
  );
}

function refreshDetails(nodes, sources, separator) {
  for (const node of nodes) {
    const column = PROBE_COLUMNS.find(
      ([id]) => id === node.dataset.probeColumnKind,
    );
    if (!column) continue;
    const probe = sources.get(column[0]);
    const detail = probeDetail(probe, column[2]);
    if (node.title === detail) continue;
    node.title = detail;
    node.setAttribute(
      "aria-label",
      `${column[2]}${separator}${probeStateLabel(probe)}: ${detail}`,
    );
  }
}

function pinColumn(cell, columnIndex) {
  const column = columnIndex + 1;
  cell.dataset.probeColumn = String(column);
  cell.style.gridColumn = String(column);
  cell.setAttribute("role", "listitem");
}

function makeCardCell(kind, icon, label, source, columnIndex) {
  const tone = probeTone(source);
  const cell = document.createElement("div");
  cell.className = `service-probe-table-cell service-probe-table-cell--${tone}`;
  cell.dataset.probeKind = kind;
  cell.dataset.probeGridCopy = "true";
  cell.dataset.probeColumnKind = kind;
  cell.title = probeDetail(source, label);
  cell.dataset.probeAvailable = String(
    Boolean(source && source.dataset.probePlaceholder !== "true"),
  );
  cell.setAttribute(
    "aria-label",
    `${label}: ${probeStateLabel(source)}: ${cell.title}`,
  );
  pinColumn(cell, columnIndex);

  const iconNode = document.createElement("span");
  iconNode.className = "service-probe-table-icon";
  iconNode.setAttribute("aria-hidden", "true");
  iconNode.textContent = icon;

  const labelNode = document.createElement("span");
  labelNode.className = "service-probe-table-label";
  labelNode.textContent = label;

  const state = document.createElement("span");
  state.className = "service-probe-table-state";
  state.textContent = probeStateLabel(source);
  cell.append(iconNode, labelNode, state);
  return cell;
}

const PROBE_PHASES = [
  ["Network", ["dns", "tcp", "tls"]],
  ["Edge", ["http", "cloudflare", "access", "service-token"]],
  ["Service", ["api", "websocket", "metrics", "policy"]],
];

// DNS and every kind seen before keep their slot (grayed when missing) so a
// refresh never adds or removes a line and resizes the card.
function observedProbes(byKind, seen) {
  return PROBE_PHASES.map(([name, kinds]) => [
    name,
    kinds
      .map((kind) => [kind, byKind.get(kind)])
      .filter(
        ([kind, probe]) =>
          kind === "dns" ||
          seen.has(kind) ||
          (probe && probe.dataset.probePlaceholder !== "true"),
      ),
  ]);
}

function renderProbePath(primary, sources, signature) {
  let path = primary.querySelector(":scope > .service-probe-path");
  if (!path) {
    path = document.createElement("div");
    path.className = "service-probe-path";
    path.setAttribute("role", "group");
    path.setAttribute("aria-label", "Observed diagnostic protocol path");
    const grid = primary.querySelector(":scope > .service-probe-table");
    if (grid) grid.insertAdjacentElement("beforebegin", path);
    else primary.appendChild(path);
  }
  if (path.dataset.signature === signature) {
    refreshDetails(
      path.querySelectorAll(".service-probe-path-step"),
      sources,
      " · ",
    );
    return;
  }
  const seen = new Set(
    String(path.dataset.seenKinds || "")
      .split(" ")
      .filter(Boolean),
  );
  for (const [kind, probe] of sources) {
    if (probe.dataset.probePlaceholder !== "true") seen.add(kind);
  }
  path.dataset.seenKinds = [...seen].join(" ");
  const groups = observedProbes(sources, seen);
  const fragment = document.createDocumentFragment();
  const heading = document.createElement("strong");
  heading.className = "service-probe-path-heading";
  heading.textContent = "Observed protocol path";
  fragment.appendChild(heading);
  for (const [phase, entries] of groups) {
    if (!entries.length) continue;
    const section = document.createElement("div");
    section.className = "service-probe-path-phase";
    const label = document.createElement("span");
    label.className = "service-probe-path-phase-label";
    label.textContent = phase;
    section.appendChild(label);
    for (const [kind, probe] of entries) {
      const column = PROBE_COLUMNS.find(([id]) => id === kind);
      const chip = document.createElement("span");
      const tone = probeTone(probe);
      chip.className =
        "service-probe-path-step service-probe-path-step--" + tone;
      chip.dataset.probeColumnKind = kind;
      const name = document.createElement("span");
      name.textContent = column?.[2] || kind;
      // Fixed-width state: "Pass" and "Warning" occupy the same space.
      const state = document.createElement("span");
      state.className = "service-probe-path-step-state";
      state.textContent = probeStateLabel(probe);
      chip.append(name, " · ", state);
      chip.title = probeDetail(probe, column?.[2] || kind);
      chip.setAttribute(
        "aria-label",
        `${name.textContent} · ${state.textContent}: ${chip.title}`,
      );
      section.appendChild(chip);
    }
    fragment.appendChild(section);
  }
  path.replaceChildren(fragment);
  path.dataset.signature = signature;
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
    grid.setAttribute("role", "list");
    grid.setAttribute(
      "aria-label",
      "Diagnostics by protocol and evidence state",
    );
    primary.appendChild(grid);
  }
  renderProbePath(primary, sources, signature);
  // Do not index placeholders as supported protocols for the filter.
  const kinds = [...sources.entries()]
    .filter(([, probe]) => probe.dataset.probePlaceholder !== "true")
    .map(([kind]) => kind);
  row.dataset.probeKinds = kinds.join(" ");
  if (grid.dataset.signature === signature) {
    refreshDetails(grid.children, sources, ": ");
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

// The detail drawer owns #service-detail-evidence; a second writer there made
// the block alternate between two layouts on every refresh.
function render() {
  scheduled = false;
  for (const row of document.querySelectorAll(ROW_SELECTOR))
    renderCardGrid(row);
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
