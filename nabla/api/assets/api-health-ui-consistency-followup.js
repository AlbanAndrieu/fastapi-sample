import { fetchHealthBoard } from "./api-health-board.js";

const PROJECT_ACCESS_POLICY = "fastapi-sample-monitor";
const PROJECT_SERVICE_AUTH = "fastapi-sample-monitor";

let latestSnapshot = null;
let scheduled = false;

function normalize(value) {
  return String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

function selectedServiceKey() {
  return String(
    document.querySelector('[data-detail-selected="true"]')?.dataset?.serviceKey ||
      "",
  ).trim();
}

function keepLastSection(selector) {
  const sections = [...document.querySelectorAll(selector)];
  for (const duplicate of sections.slice(0, -1)) duplicate.remove();
  return sections.at(-1) || null;
}

function providerItem(section, label) {
  const expected = normalize(label);
  return [...section.querySelectorAll(".service-provider-item")].find(
    (item) =>
      normalize(item.querySelector(":scope > div > strong")?.textContent) ===
      expected,
  );
}

function familyCount(family) {
  const value = Number(family?.total_count ?? family?.result_count);
  return Number.isFinite(value) ? value : null;
}

function familyError(family) {
  if (!family) return "inventory not confirmed";
  if (family.success === false || family.state === "error") {
    return `inventory unavailable${family.error ? ` · ${family.error}` : ""}`;
  }
  return "";
}

function setProviderDetail(item, detail, tone = "ok") {
  if (!item) return;
  const text = item.querySelector(":scope > div > span");
  if (text && text.textContent !== detail) text.textContent = detail;
  item.title = detail;
  for (const candidate of ["ok", "warn", "fail", "neutral"]) {
    item.classList.remove(`service-provider-item--${candidate}`);
  }
  item.classList.add(`service-provider-item--${tone}`);
}

function removeDuplicateProviderItems(section) {
  const seen = new Set();
  for (const item of [...section.querySelectorAll(".service-provider-item")].reverse()) {
    const label = normalize(
      item.querySelector(":scope > div > strong")?.textContent,
    );
    if (!label || !seen.has(label)) {
      if (label) seen.add(label);
      continue;
    }
    item.remove();
  }
}

function removeCloudflareSummaryDuplicates(drawer, accessItem) {
  const canonicalText = normalize(
    accessItem?.querySelector(":scope > div > span")?.textContent,
  );
  if (!canonicalText) return;
  for (const node of drawer.querySelectorAll(
    ".service-detail-metric, .service-provider-summary",
  )) {
    if (node.closest(".service-provider-item") === accessItem) continue;
    const text = normalize(node.textContent);
    if (text === canonicalText || text.endsWith(canonicalText)) node.remove();
  }
}

function reconcileCloudflare(section, drawer) {
  const control = latestSnapshot?.homelab?.cloudflare?.control_plane || {};
  const apps = control.access_applications;
  const policies = control.access_reusable_policies;
  const tokens = control.access_service_tokens;

  const accessItem = providerItem(section, "Access applications");
  const appError = familyError(apps);
  const appCount = familyCount(apps);
  setProviderDetail(
    accessItem,
    appError ||
      (appCount == null
        ? "inventory not confirmed"
        : `${appCount} application(s) visible`),
    appError ? "warn" : appCount == null ? "neutral" : "ok",
  );

  const policyItem = providerItem(section, "Reusable policies");
  const policyError = familyError(policies);
  const policyCount = familyCount(policies);
  setProviderDetail(
    policyItem,
    policyError ||
      (policyCount == null
        ? `${PROJECT_ACCESS_POLICY} · inventory not confirmed`
        : `${policyCount} project polic${policyCount === 1 ? "y" : "ies"} visible · ${PROJECT_ACCESS_POLICY}`),
    policyError ? "warn" : policyCount == null ? "neutral" : "ok",
  );

  const tokenItem = providerItem(section, "Service Tokens");
  const tokenError = familyError(tokens);
  const tokenCount = familyCount(tokens);
  const present = tokens?.configured_client_id_present;
  const tokenPresence =
    present === true
      ? "configured Service Auth found"
      : present === false
        ? "configured Service Auth not found"
        : "Service Auth correlation not confirmed";
  setProviderDetail(
    tokenItem,
    tokenError ||
      (tokenCount == null
        ? `${PROJECT_SERVICE_AUTH} · ${tokenPresence}`
        : `${tokenCount} project Service Token${tokenCount === 1 ? "" : "s"} visible · ${PROJECT_SERVICE_AUTH} · ${tokenPresence}`),
    tokenError || present === false
      ? "warn"
      : tokenCount == null
        ? "neutral"
        : "ok",
  );

  removeDuplicateProviderItems(section);
  removeCloudflareSummaryDuplicates(drawer, accessItem);
}

function reconcileDrawer() {
  scheduled = false;
  const drawer = document.getElementById("service-detail-drawer");
  if (!drawer || drawer.hidden) return;

  keepLastSection("#service-detail-drawer [data-probe-timing-section]");
  const provider = keepLastSection(
    "#service-detail-drawer [data-provider-diagnostics-section]",
  );
  if (selectedServiceKey() === "cloudflare" && provider) {
    reconcileCloudflare(provider, drawer);
  }
}

function schedule() {
  if (scheduled) return;
  scheduled = true;
  window.requestAnimationFrame(reconcileDrawer);
}

async function refresh() {
  latestSnapshot = await fetchHealthBoard().catch(() => latestSnapshot);
  schedule();
}

function observeDrawer() {
  const drawer = document.getElementById("service-detail-drawer");
  if (!drawer) return;
  new MutationObserver(schedule).observe(drawer, {
    childList: true,
    subtree: true,
  });
}

export function installHealthUiConsistencyFollowup() {
  observeDrawer();
  document.addEventListener("health-board-refreshed", refresh);
  document.addEventListener("service-filter-changed", schedule);
  document.addEventListener("click", (event) => {
    if (event.target instanceof Element && event.target.closest(".service-detail-trigger")) {
      window.setTimeout(schedule, 0);
    }
  });
  refresh();
}
