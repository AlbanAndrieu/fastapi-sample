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
    document.querySelector('[data-detail-selected="true"]')?.dataset
      ?.serviceKey || "",
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
  for (const item of [
    ...section.querySelectorAll(".service-provider-item"),
  ].reverse()) {
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

function isLegacyCloudflareSummary(text) {
  const value = normalize(text);
  return (
    /^\d+ application\(s\) visible$/.test(value) ||
    /^\d+ policy object\(s\) visible$/.test(value) ||
    /^\d+ service token\(s\) visible$/.test(value) ||
    value.includes("project service token") ||
    value.includes("project policy visible")
  );
}

function removeCloudflareSummaryDuplicates(drawer) {
  for (const node of drawer.querySelectorAll(
    ".service-detail-metric, .service-provider-summary",
  )) {
    if (isLegacyCloudflareSummary(node.textContent)) node.remove();
  }
}

function reconcileCloudflare(section, drawer) {
  const control = latestSnapshot?.homelab?.cloudflare?.control_plane || {};
  const apps = control.access_applications;
  const policies = control.access_reusable_policies;
  const tokens = control.access_service_tokens;

  const accessItem = providerItem(section, "Access applications");
  const appError = familyError(apps);
  setProviderDetail(
    accessItem,
    appError || "inventory confirmed",
    appError ? "warn" : apps ? "ok" : "neutral",
  );

  const policyItem = providerItem(section, "Reusable policies");
  const policyError = familyError(policies);
  setProviderDetail(
    policyItem,
    policyError || PROJECT_ACCESS_POLICY,
    policyError ? "warn" : policies ? "ok" : "neutral",
  );

  const tokenItem = providerItem(section, "Service Tokens");
  const tokenError = familyError(tokens);
  const present = tokens?.configured_client_id_present;
  const tokenPresence =
    present === true
      ? "configured Service Auth found"
      : present === false
        ? "configured Service Auth not found"
        : "Service Auth correlation not confirmed";
  setProviderDetail(
    tokenItem,
    tokenError || `${PROJECT_SERVICE_AUTH} · ${tokenPresence}`,
    tokenError || present === false
      ? "warn"
      : tokens
        ? "ok"
        : "neutral",
  );

  removeDuplicateProviderItems(section);
  removeCloudflareSummaryDuplicates(drawer);
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
    if (
      event.target instanceof Element &&
      event.target.closest(".service-detail-trigger")
    ) {
      window.setTimeout(schedule, 0);
    }
  });
  refresh();
}
