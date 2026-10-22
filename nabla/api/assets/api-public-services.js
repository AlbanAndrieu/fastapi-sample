import { ownerSessionAvailable } from "./api-owner-session.js";

// Minimal public projection ONLY; no private probe URLs or credentials.
const PREVIEW_LIMIT = 36;
const STATES = new Set(["ok", "warn", "fail", "unknown"]);
const KINDS = new Set(["API", "Component", "Resource"]);

function validOverview(value) {
  return (
    value &&
    value.schemaVersion === 2 &&
    value.model === "public-service-overview" &&
    /^sha256:[a-f0-9]{64}$/.test(value.catalogRevision || "") &&
    ["fresh", "stale", "pending"].includes(value.boardState) &&
    Array.isArray(value.services) &&
    value.services.length <= 2000 &&
    value.services.every(
      (service) =>
        service &&
        typeof service.name === "string" &&
        service.name.length > 0 &&
        service.name.length <= 128 &&
        KINDS.has(service.kind) &&
        STATES.has(service.state),
    )
  );
}

export async function installPublicServiceOverview() {
  const panel = document.getElementById("public-services-panel");
  const list = document.getElementById("public-services-list");
  const summary = document.getElementById("public-services-summary");
  const refresh = document.getElementById("public-services-refresh");
  const expand = document.getElementById("public-services-show-all");
  const filter = document.getElementById("service-filter");
  if (!panel || !list || !summary || !refresh || !expand) return;

  // When the full owner dashboard works, do not duplicate its service cards.
  if (await ownerSessionAvailable()) return;
  panel.hidden = false;
  let rows = [];
  let expanded = false;
  let pendingRetries = 0;

  function render() {
    const query = (filter?.value || "").trim().toLowerCase();
    const matching = rows.filter((entry) =>
      (entry.name + " " + entry.kind + " " + entry.state)
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
      const label = document.createElement("span");
      label.textContent = service.name;
      const state = document.createElement("strong");
      state.className =
        "public-service-state public-service-state--" + service.state;
      state.textContent = service.state.toUpperCase();
      state.title =
        service.state === "unknown"
          ? "No confirmed fresh observation"
          : "Summarized service observation (not a full health audit)";
      item.append(label, state);
      fragment.appendChild(item);
    }
    list.replaceChildren(fragment);
    expand.hidden = matching.length <= PREVIEW_LIMIT;
    expand.textContent = expanded
      ? "Show fewer"
      : "Show all " + matching.length + " services";
  }

  let loading = false;
  async function load() {
    if (loading) return;
    loading = true;
    refresh.disabled = true;
    summary.textContent = "Loading the limited service directory…";
    try {
      const response = await fetch("/api/ui/services", {
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (!response.ok)
        throw new Error("Unavailable (HTTP " + response.status + ")");
      const payload = await response.json();
      if (!validOverview(payload))
        throw new Error("Invalid service directory response");
      // Never label expired probe observations as healthy or failing.
      rows = payload.services.map((service) => ({
        ...service,
        state: payload.boardState === "fresh" ? service.state : "unknown",
      }));
      summary.dataset.serviceCount = String(rows.length);
      const counts = { ok: 0, warn: 0, fail: 0, unknown: 0 };
      for (const row of rows) counts[row.state] += 1;
      summary.textContent =
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
        (payload.boardState !== "fresh"
          ? " · observations pending or stale"
          : "") +
        " · raw probes locked";
      render();
      // A cold cloud cache may be pending for the first 40-second refresh.
      // Keep probes server-owned: at most five UI polls, then manual refresh.
      if (payload.boardState !== "fresh" && pendingRetries < 5) {
        pendingRetries += 1;
        window.setTimeout(() => {
          if (!document.hidden && !panel.hidden) void load();
        }, 9000);
      }
    } catch {
      // Keep a previously loaded roster in memory when refresh fails, but
      // revoke every stale health assertion until new evidence is verified.
      if (rows.length > 0) {
        rows = rows.map((service) => ({ ...service, state: "unknown" }));
        summary.textContent =
          rows.length +
          " services listed · observations unavailable, all statuses UNKNOWN";
        render();
      } else {
        delete summary.dataset.serviceCount;
        list.replaceChildren();
        expand.hidden = true;
        summary.textContent =
          "Service directory temporarily unavailable. Owner diagnostics remain locked.";
      }
    } finally {
      loading = false;
      refresh.disabled = false;
    }
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
  refresh.addEventListener("click", () => void load());
  await load();
}
