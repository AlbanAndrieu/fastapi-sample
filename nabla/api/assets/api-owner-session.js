// Owner UI authentication: never persist the diagnostics key in browser storage.
let statusPromise = null;

export function resetOwnerSessionStatus() {
  statusPromise = null;
}

export async function ownerSessionAvailable() {
  if (!statusPromise) {
    statusPromise = fetch("/api/ui/session", {
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json" },
    })
      .then(async (response) =>
        response.ok && (await response.json()).authenticated === true,
      )
      .catch(() => false);
  }
  return statusPromise;
}

export function installOwnerSessionControls(onAuthenticated) {
  const state = document.getElementById("owner-session-state");
  const login = document.getElementById("owner-session-login");
  const logout = document.getElementById("owner-session-logout");
  const form = document.getElementById("owner-session-form");
  const input = document.getElementById("owner-session-key");
  const cancel = document.getElementById("owner-session-cancel");
  if (!state || !login || !logout || !form || !input || !cancel) return;

  function update(authenticated) {
    state.textContent = authenticated
      ? "Owner diagnostics unlocked (network-restricted, 20 minute session)."
      : "Owner diagnostics are locked. Public liveness remains available.";
    login.hidden = authenticated;
    logout.hidden = !authenticated;
    form.hidden = true;
    input.value = "";
  }

  ownerSessionAvailable().then(update);
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
    try {
      const response = await fetch("/api/ui/session", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: { "X-Diagnostics-Key": key, Accept: "application/json" },
      });
      if (!response.ok) throw new Error("Access denied (HTTP " + response.status + ")");
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
