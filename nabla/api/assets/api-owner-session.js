// Owner UI authentication: never persist the diagnostics key in browser storage.
import { withRequestDeadline } from "./api-request-deadline.js";

const SESSION_DEADLINE_MS = 4500;
let statusPromise = null;

export function resetOwnerSessionStatus() {
  statusPromise = null;
}

async function sessionCapabilities() {
  if (!statusPromise) {
    statusPromise = withRequestDeadline(async (signal) => {
      const response = await fetch("/api/ui/session", {
        signal,
        credentials: "same-origin",
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) return { authenticated: false, readOnly: false };
      const status = await response.json();
      return {
        authenticated: status.authenticated === true,
        readOnly: status.readOnlyDiagnostics === true,
      };
    }, SESSION_DEADLINE_MS).catch(() => ({
      // Fail closed for diagnostic/owner capabilities; the public directory
      // is rendered separately without an owner session.
      authenticated: false,
      readOnly: false,
    }));
  }
  return statusPromise;
}

// Authentication and the temporary public read capability are distinct.
// Mutation controls MUST depend on ownerSessionAvailable alone.
export async function ownerSessionAvailable() {
  return (await sessionCapabilities()).authenticated;
}

export async function diagnosticsReadAvailable() {
  const status = await sessionCapabilities();
  return status.authenticated || status.readOnly;
}

export function installOwnerSessionControls(onAuthenticated) {
  const state = document.getElementById("owner-session-state");
  const login = document.getElementById("owner-session-login");
  const logout = document.getElementById("owner-session-logout");
  const form = document.getElementById("owner-session-form");
  const input = document.getElementById("owner-session-key");
  const cancel = document.getElementById("owner-session-cancel");
  if (!state || !login || !logout || !form || !input || !cancel) return;
  // Entry and rich dashboard may both request installation. Bind once only.
  if (form.dataset.ownerSessionInitialized === "1") return;
  form.dataset.ownerSessionInitialized = "1";

  function update(authenticated) {
    state.textContent = authenticated
      ? "Owner authorized (20 minute session). Use Open detailed diagnostics for service probes."
      : "Owner diagnostics are locked. Public liveness remains available.";
    login.hidden = authenticated;
    logout.hidden = !authenticated;
    form.hidden = true;
    input.value = "";
  }

  // Re-check a short-lived signed session when returning to the app.
  // Network transitions do not grant OWNER access; the server still checks
  // the source IP and the signed cookie. Never read or retain the key.
  let sessionCheck = 0;
  function refreshStatus() {
    // Do not erase a key currently being entered while changing networks.
    if (!form.hidden) return;
    const check = ++sessionCheck;
    resetOwnerSessionStatus();
    void ownerSessionAvailable().then((authenticated) => {
      if (check === sessionCheck && form.hidden) update(authenticated);
    });
  }
  refreshStatus();
  window.addEventListener("online", refreshStatus);
  window.addEventListener("pageshow", refreshStatus);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refreshStatus();
  });
  login.addEventListener("click", () => {
    form.hidden = false;
    input.focus();
  });
  cancel.addEventListener("click", () => {
    input.value = "";
    form.hidden = true;
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const key = input.value.trim();
    input.value = "";
    if (!key) return;
    // Ignore earlier unauthenticated status requests during this login.
    sessionCheck += 1;
    try {
      const response = await fetch("/api/ui/session", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: { "X-Diagnostics-Key": key, Accept: "application/json" },
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        const reason = payload?.code;
        if (response.status === 401) {
          throw new Error("Incorrect diagnostics key (HTTP 401).");
        }
        if (response.status === 503 || reason === "unconfigured") {
          throw new Error(
            "Owner access is not configured on this FastAPI runtime (HTTP 503).",
          );
        }
        if (
          reason === "origin_unverified" ||
          payload?.detail === "Same-origin request required"
        ) {
          throw new Error(
            "Browser same-origin verification failed (HTTP 403).",
          );
        }
        if (response.status === 403 && reason === "source_unverified") {
          throw new Error(
            "Home IP could not be verified by FastAPI Cloud (HTTP 403). " +
              "Check the trusted source and proxy settings; your key was not checked.",
          );
        }
        if (response.status === 403) {
          throw new Error(
            "Owner access denied (HTTP 403). Check the response code " +
              "in Network; your diagnostics key may not have been checked.",
          );
        }
        throw new Error(
          "Diagnostics login unavailable (HTTP " + response.status + ").",
        );
      }
      resetOwnerSessionStatus();
      update(true);
      onAuthenticated();
    } catch (error) {
      update(false);
      state.textContent = String(error?.message || error);
    }
  });
  logout.addEventListener("click", async () => {
    try {
      await fetch("/api/ui/session/logout", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
      });
    } finally {
      resetOwnerSessionStatus();
      update(false);
      window.location.reload();
    }
  });
}
