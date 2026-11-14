import {
  clearPublicObservation,
  publicObservationAge,
  publicObservationStorage,
  readPublicObservation,
  savePublicObservation,
} from "./api-public-observation-cache.js";
import { withRequestDeadline } from "./api-request-deadline.js";

// Minimal public projection ONLY; no private probe URLs or credentials.
const PREVIEW_LIMIT = 36;
const STATES = new Set(["ok", "warn", "fail", "unknown"]);
const KINDS = new Set(["API", "Component", "Resource"]);
const SAFE_TAG = /^[a-z0-9][a-z0-9-]{0,63}$/;

export function publicServiceSubtitle(service) {
  const type = service.serviceType || service.kind;
  const tags = Array.isArray(service.tags) ? service.tags.slice(0, 3) : [];
  return [type, ...tags].join(" · ");
}

export function validOverview(value) {
  return (
    value &&
    value.schemaVersion === 2 &&
    value.model === "public-service-overview" &&
    /^sha256:[a-f0-9]{64}$/.test(value.catalogRevision || "") &&
    ["fresh", "stale", "pending"].includes(value.boardState) &&
    ["backstage-v2", "bootstrap-snapshot"].includes(
      value.catalogSource || "backstage-v2",
    ) &&
    Array.isArray(value.services) &&
    value.services.length <= 2000 &&
    value.services.every(
      (service) =>
        service &&
        typeof service.name === "string" &&
        service.name.length > 0 &&
        service.name.length <= 128 &&
        KINDS.has(service.kind) &&
        STATES.has(service.state) &&
        (service.serviceType == null ||
          (typeof service.serviceType === "string" &&
            SAFE_TAG.test(service.serviceType))) &&
        (service.tags == null ||
          (Array.isArray(service.tags) &&
            service.tags.length <= 3 &&
            service.tags.every(
              (tag) => typeof tag === "string" && SAFE_TAG.test(tag),
            ))),
    )
  );
}

// This view is never a private probe cache. A restored state is labelled
// HISTORICAL, grey, and dated until the server confirms a fresh new snapshot.
const CLOUD_RECHECK_MS = 180000;
const LOCAL_RECHECK_MS = 30000;
const DISPLAY_FRESH_MS = 90000;
const PENDING_RETRY_BASE_MS = 9000;
const PENDING_RETRY_CAP_MS = 90000;

export function reconcilePublicObservation(payload, cached) {
  if (
    payload.boardState === "fresh" &&
    payload.catalogSource === "backstage-v2"
  ) {
    return { rows: payload.services, historical: false };
  }
  if (cached?.catalogRevision === payload.catalogRevision) {
    return { rows: cached.services, historical: true };
  }
  return {
    rows: payload.services.map((service) => ({ ...service, state: "unknown" })),
    historical: false,
  };
}

export async function installPublicServiceOverview({
  ownerAuthenticated = false,
} = {}) {
  const panel = document.getElementById("public-services-panel");
  const list = document.getElementById("public-services-list");
  const summary = document.getElementById("public-services-summary");
  const refresh = document.getElementById("public-services-refresh");
  const expand = document.getElementById("public-services-show-all");
  const filter = document.getElementById("service-filter");
  if (!panel || !list || !summary || !refresh || !expand) return;

  if (ownerAuthenticated || panel.dataset.publicServicesInitialized === "1")
    return;
  panel.dataset.publicServicesInitialized = "1";
  panel.hidden = false;

  const storage = publicObservationStorage();
  const recheckMs = window.location?.hostname?.endsWith(".fastapicloud.dev")
    ? CLOUD_RECHECK_MS
    : LOCAL_RECHECK_MS;
  let rows = [];
  let expanded = false;
  let historical = false;
  let receivedAt = null;
  let catalogRevision = null;
  let catalogSource = "backstage-v2";
  let pendingRetries = 0;
  let loading = false;
  let retryTimer = null;
  let lastAttemptAt = 0;
  let awaitingFreshEvidence = false;

  function countsForRows() {
    const counts = { ok: 0, warn: 0, fail: 0, unknown: 0 };
    for (const row of rows) counts[row.state] += 1;
    return counts;
  }

  function renderPublicSummary(counts, total) {
    const overview = document.getElementById("service-health-overview");
    if (!overview) return;
    overview.dataset.historical = historical ? "true" : "false";
    const cards = overview.querySelectorAll(".service-overview-card");
    if (cards.length !== 5) return;
    const values =
      counts === null
        ? ["Unavailable", "—", "—", "—", "—"]
        : [
            total + " listed",
            String(counts.ok),
            String(counts.warn),
            String(counts.fail),
            String(counts.unknown),
          ];
    const labels = ["Services", "Healthy", "Degraded", "Failed", "Unconfirmed"];
    const detail = historical
      ? "Last public response " +
        publicObservationAge(receivedAt) +
        " ago · not a current probe"
      : catalogSource === "bootstrap-snapshot"
        ? "Last-known local inventory (not live)"
        : "Verified public summary (not full health audit)";
    cards.forEach((card, index) => {
      const heading = card.querySelector("span");
      const value = card.querySelector("strong");
      const description = card.querySelector("small");
      if (heading) heading.textContent = labels[index];
      if (value) value.textContent = values[index];
      if (description) description.textContent = detail;
    });
  }

  function render() {
    const query = (filter?.value || "").trim().toLowerCase();
    const matching = rows.filter((entry) =>
      [
        entry.name,
        entry.kind,
        entry.state,
        entry.serviceType || "",
        ...(entry.tags || []),
      ]
        .join(" ")
        .toLowerCase()
        .includes(query),
    );
    const visible = matching.slice(
      0,
      expanded ? matching.length : PREVIEW_LIMIT,
    );
    const fragment = document.createDocumentFragment();
    for (const service of visible) {
      const item = document.createElement("li");
      item.className = "public-service-card";
      const identity = document.createElement("span");
      identity.className = "public-service-identity";
      const label = document.createElement("span");
      label.className = "public-service-name";
      label.textContent = service.name;
      const meta = document.createElement("small");
      meta.className = "public-service-meta";
      meta.textContent = publicServiceSubtitle(service);
      identity.append(label, meta);
      const state = document.createElement("strong");
      state.className =
        "public-service-state public-service-state--" +
        (historical ? "historical" : service.state);
      state.textContent = historical
        ? "LAST " + service.state.toUpperCase()
        : service.state.toUpperCase();
      state.title = historical
        ? "Last public response " +
          publicObservationAge(receivedAt) +
          " ago; current probe is unverified"
        : service.state === "unknown"
          ? "No confirmed fresh observation"
          : "Summarized public observation (not a full health audit)";
      item.append(identity, state);
      fragment.appendChild(item);
    }
    list.replaceChildren(fragment);
    expand.hidden = matching.length <= PREVIEW_LIMIT;
    expand.textContent = expanded
      ? "Show fewer"
      : "Show all " + matching.length + " services";
  }

  function updateSummary(note = "") {
    const counts = countsForRows();
    renderPublicSummary(rows.length ? counts : null, rows.length);
    summary.dataset.serviceCount = String(rows.length);
    summary.dataset.catalogSource = catalogSource;
    summary.dataset.snapshotKind = historical ? "historical" : "current";
    if (receivedAt != null) summary.dataset.lastReceivedAt = String(receivedAt);
    else delete summary.dataset.lastReceivedAt;
    const prefix =
      historical && receivedAt != null
        ? "Last public response " +
          publicObservationAge(receivedAt) +
          " ago · historical only, not current · "
        : catalogSource === "bootstrap-snapshot"
          ? "Bootstrap inventory · "
          : "";
    summary.textContent =
      prefix +
      rows.length +
      " services · " +
      counts.ok +
      " OK · " +
      counts.warn +
      " WARN · " +
      counts.fail +
      " FAIL · " +
      counts.unknown +
      " UNKNOWN" +
      (note ? " · " + note : "") +
      " · detailed probes require authorization";
    render();
  }

  function lastKnownOnError() {
    if (rows.length > 0 && receivedAt != null) {
      historical = true;
      updateSummary("Refresh unavailable; last known values retained");
    } else if (rows.length > 0) {
      rows = rows.map((service) => ({ ...service, state: "unknown" }));
      historical = false;
      updateSummary("Current observations unavailable");
    } else {
      renderPublicSummary(null, 0);
      delete summary.dataset.serviceCount;
      list.replaceChildren();
      expand.hidden = true;
      summary.textContent =
        "Service inventory unavailable; no verified names or statuses to display.";
    }
  }

  function clearRetry() {
    if (retryTimer !== null) window.clearTimeout(retryTimer);
    retryTimer = null;
  }

  function schedulePendingRetry() {
    clearRetry();
    if (pendingRetries >= 5 || document.hidden) return;
    const delay = Math.min(
      PENDING_RETRY_CAP_MS,
      PENDING_RETRY_BASE_MS * 2 ** pendingRetries,
    );
    pendingRetries += 1;
    retryTimer = window.setTimeout(() => {
      retryTimer = null;
      if (!document.hidden && !panel.hidden) void load();
    }, delay);
  }

  function expireLiveView() {
    if (
      !historical &&
      receivedAt != null &&
      Date.now() - receivedAt > DISPLAY_FRESH_MS
    ) {
      historical = true;
      updateSummary("Revalidating");
    }
  }

  async function load({ manual = false } = {}) {
    if (loading || document.hidden) return;
    if (manual) {
      pendingRetries = 0;
      clearRetry();
    }
    loading = true;
    lastAttemptAt = Date.now();
    refresh.disabled = true;
    if (!rows.length)
      summary.textContent = "Loading the limited service directory…";
    else if (historical) updateSummary("Updating in background");
    try {
      const payload = await withRequestDeadline(async (signal) => {
        const response = await fetch("/api/ui/services", {
          signal,
          cache: "no-store",
          headers: { Accept: "application/json" },
        });
        if (
          response.status === 401 ||
          response.status === 403 ||
          response.status === 404
        ) {
          const error = new Error("Public directory access unavailable");
          error.code = "public_access_disabled";
          throw error;
        }
        if (!response.ok)
          throw new Error("Unavailable (HTTP " + response.status + ")");
        return response.json();
      }, 6500);
      if (!validOverview(payload))
        throw new Error("Invalid service directory response");

      const previous =
        receivedAt != null ? { catalogRevision, services: rows } : null;
      const projected = reconcilePublicObservation(payload, previous);
      rows = projected.rows;
      historical = projected.historical;
      catalogSource = payload.catalogSource || "backstage-v2";
      if (
        !historical &&
        payload.boardState === "fresh" &&
        catalogSource === "backstage-v2"
      ) {
        receivedAt = Date.now();
        catalogRevision = payload.catalogRevision;
        savePublicObservation(storage, payload, receivedAt);
        pendingRetries = 0;
        awaitingFreshEvidence = false;
        clearRetry();
        updateSummary("Current public summary");
      } else {
        awaitingFreshEvidence = true;
        if (catalogRevision !== payload.catalogRevision) {
          clearPublicObservation(storage);
          receivedAt = null;
          catalogRevision = payload.catalogRevision;
        }
        updateSummary("New probe evidence pending or stale");
        schedulePendingRetry();
      }
    } catch (error) {
      if (error?.code === "public_access_disabled") {
        clearPublicObservation(storage);
        rows = [];
        receivedAt = null;
        catalogRevision = null;
        awaitingFreshEvidence = false;
        lastKnownOnError();
      } else {
        awaitingFreshEvidence = true;
        lastKnownOnError();
        // Retain the historical PUBLIC-only view and retry with bounded
        // backoff instead of requiring a manual Refresh after a cold start.
        schedulePendingRetry();
      }
    } finally {
      loading = false;
      refresh.disabled = false;
    }
  }

  function resume({ immediate = false } = {}) {
    if (document.hidden) return;
    // Expire the status even when a detailed board had hidden the public
    // fallback. A stale/pending detailed board may reveal it again.
    expireLiveView();
    if (panel.hidden) return;
    const delay = immediate ? 5000 : awaitingFreshEvidence ? 9000 : recheckMs;
    if (Date.now() - lastAttemptAt < delay || loading) return;
    pendingRetries = 0;
    clearRetry();
    void load();
  }

  const cached = readPublicObservation(storage);
  if (cached) {
    rows = cached.directory.services;
    receivedAt = cached.receivedAt;
    catalogRevision = cached.directory.catalogRevision;
    historical = true;
    updateSummary("Updating in background");
  }

  filter?.addEventListener("input", render);
  document
    .getElementById("service-filter-clear")
    ?.addEventListener("click", () => {
      window.setTimeout(render, 0);
    });
  expand.addEventListener("click", () => {
    expanded = !expanded;
    render();
  });
  refresh.addEventListener("click", () => void load({ manual: true }));
  document.addEventListener("visibilitychange", resume);
  window.addEventListener("pageshow", resume);
  window.addEventListener("online", () => resume({ immediate: true }));
  if (!document.hidden) await load();
}
