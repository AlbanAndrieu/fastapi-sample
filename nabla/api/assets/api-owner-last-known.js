// Historical OWNER evidence is read once on entering the detailed dashboard.
// Never persist it in localStorage, sessionStorage or the service worker.

import { ownerSessionAvailable } from "./api-owner-session.js";
import { withRequestDeadline } from "./api-request-deadline.js";

const VALID_ID = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$/;
const VALID_STATES = new Set(["ok", "warn", "fail", "expected"]);
const MAX_VISIBLE = 75;
let installed = false;
let revision = 0;
let pending = null;
let freshEvidence = false;

function clearHistory() {
  revision += 1;
  pending = null;
  document.getElementById("owner-last-known-evidence")?.remove();
}

function onBoardRefresh(event) {
  freshEvidence =
    event.detail?.state === "fresh" &&
    event.detail?.refreshing !== true &&
    event.detail?.serviceEvidenceCount > 0;
  const panel = document.getElementById("owner-last-known-evidence");
  if (panel) panel.hidden = freshEvidence;
}

export function normalizeOwnerLastKnown(payload) {
  if (payload?.state !== "historical" || payload.current !== false) return [];
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
  if (!anchor?.parentElement) return;
  if (!rows.length) {
    document.getElementById("owner-last-known-evidence")?.remove();
    return;
  }
  let panel = document.getElementById("owner-last-known-evidence");
  if (!panel) {
    panel = document.createElement("details");
    panel.id = "owner-last-known-evidence";
    panel.className = "owner-last-known-evidence";
    anchor.parentElement.appendChild(panel);
  }
  panel.hidden = freshEvidence;
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
}

function loadHistory() {
  if (pending) return pending;
  const token = ++revision;
  const job = (async () => {
    try {
      if (!(await ownerSessionAvailable())) {
        if (token === revision) clearHistory();
        return;
      }
      const payload = await withRequestDeadline(async (signal) => {
        const response = await fetch("/api/health-board/last-known", {
          signal,
          credentials: "same-origin",
          cache: "no-store",
          headers: { Accept: "application/json" },
        });
        if (response.status === 401 || response.status === 403) {
          if (token === revision) clearHistory();
          return null;
        }
        if (!response.ok) return null;
        return response.json();
      }, 2200);
      if (token === revision && payload) {
        showHistoricalRows(normalizeOwnerLastKnown(payload));
      }
    } catch {
      // A public or stale board can still render without OWNER Redis.
    }
  })();
  pending = job;
  void job.finally(() => {
    if (pending === job) pending = null;
  });
  return job;
}

export function installOwnerLastKnown() {
  if (installed) return;
  installed = true;
  document.addEventListener("health-board-refreshed", onBoardRefresh);
  document.addEventListener("owner-session-changed", (event) => {
    if (event.detail?.authenticated === true) void loadHistory();
    else clearHistory();
  });
  void loadHistory();
}
