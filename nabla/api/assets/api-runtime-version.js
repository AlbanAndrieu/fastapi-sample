const VERSION_REFRESH_MS = 5 * 60 * 1000;

function warningElement() {
  return document.getElementById("runtime-version-warning");
}

export async function loadRuntimeVersionStatus() {
  const warning = warningElement();
  if (!warning) return;
  try {
    const response = await fetch("/api/runtime/version-status", {
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (data?.behind === true && data?.cloud_version) {
      warning.hidden = false;
      warning.textContent = "⚠️";
      warning.title = `Local service ${data.local_version} is behind FastAPI Cloud ${data.cloud_version}. Update the TrueNAS service.`;
      warning.setAttribute("aria-label", warning.title);
      return;
    }
    warning.hidden = true;
    warning.removeAttribute("title");
    warning.removeAttribute("aria-label");
  } catch {
    warning.hidden = true;
  }
}

export function startRuntimeVersionMonitor() {
  loadRuntimeVersionStatus();
  window.setInterval(loadRuntimeVersionStatus, VERSION_REFRESH_MS);
}
