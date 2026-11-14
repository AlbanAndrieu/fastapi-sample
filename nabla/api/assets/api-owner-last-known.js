// Historical OWNER evidence is read once on entering the detailed dashboard.
// Never persist it in localStorage, sessionStorage or the service worker.
import { withRequestDeadline } from "./api-request-deadline.js";
import { ownerSessionAvailable } from "./api-owner-session.js";

const VALID_ID = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$/;
const VALID_STATES = new Set(["ok", "warn", "fail", "expected"]);
const MAX_VISIBLE = 75;

export function normalizeOwnerLastKnown(payload) {
  if (payload?.state !== "historical" || payload.current !== false)
    return [];
  if (!Array.isArray(payload.observations)) return [];
  return payload.observations
    .filter(
      (row) =>
        row &&
        typeof row.id === "string" &&
        VALID_ID.test(row.id) &&
        VALID_STATES.has(row.state) &&
        ["public", "internal"].includes(row.scope) &&
        Number.isFinite(row.ageSeconds) &&
        row.ageSeconds >= 0 &&
        row.ageSeconds <= 7 * 86400 &&
        typeof row.observedAt === "string" &&
        !Number.isNaN(Date.parse(row.observedAt)),
    )
    .slice(0, 512)
    .map(({ id, state, scope, observedAt, ageSeconds }) => ({
      id,
      state,
      scope,
      observedAt,
      ageSeconds,
    }));
}

function ageLabel(seconds) {
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h`;
  return `${Math.floor(seconds / 86400)} d`;
}

function showHistoricalRows(rows) {
  const anchor = document.getElementById("health-board-freshness");
  if (!anchor?.parentElement || !rows.length) return;
  let panel = document.getElementById("owner-last-known-evidence");
  if (!panel) {
    panel = document.createElement("details");
    panel.id = "owner-last-known-evidence";
    panel.className = "owner-last-known-evidence";
    anchor.parentElement.appendChild(panel);
  }
  panel.replaceChildren();
  const heading = document.createElement("summary");
  heading.textContent = `Last known OWNER observations (${rows.length}) · historical, not live`;
  panel.appendChild(heading);
  const list = document.createElement("ul");
  for (const row of rows.slice(0, MAX_VISIBLE)) {
    const item = document.createElement("li");
    item.textContent = `${row.id} · ${row.scope} · ${row.state} ${ageLabel(row.ageSeconds)} ago (historical)`;
    list.appendChild(item);
  }
  if (rows.length > MAX_VISIBLE) {
    const omitted = document.createElement("li");
    omitted.textContent = `${rows.length - MAX_VISIBLE} additional historical observations not displayed`;
    list.appendChild(omitted);
  }
  panel.appendChild(list);
  document.addEventListener("health-board-refreshed", (event) => {
    panel.hidden = event.detail?.state === "fresh" &&
      event.detail?.serviceEvidenceCount > 0;
  });
}

export async function installOwnerLastKnown() {
  if (!(await ownerSessionAvailable())) return;
  try {
    const payload = await withRequestDeadline(async (signal) => {
      const response = await fetch("/api/health-board/last-known", {
        signal,
        credentials: "same-origin",
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) return null;
      return response.json();
    }, 2200);
    showHistoricalRows(normalizeOwnerLastKnown(payload));
  } catch {
    // Existing live dashboard and PUBLIC fallback remain available.
  }
}
