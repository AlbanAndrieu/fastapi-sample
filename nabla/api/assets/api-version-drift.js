const FASTAPI_CLOUD_VERSION_URL =
  "https://fastapi-sample.fastapicloud.dev/api/runtime-version";

function semverParts(value) {
  const match = String(value || "").match(/(\d+)\.(\d+)\.(\d+)/);
  return match ? match.slice(1, 4).map(Number) : null;
}

function compareVersions(left, right) {
  const a = semverParts(left);
  const b = semverParts(right);
  if (!a || !b) return null;
  for (let index = 0; index < 3; index += 1) {
    if (a[index] !== b[index]) return a[index] < b[index] ? -1 : 1;
  }
  return 0;
}

function ensureWarning(versionNode) {
  let warning = document.getElementById("runtime-version-drift-warning");
  if (warning) return warning;
  warning = document.createElement("span");
  warning.id = "runtime-version-drift-warning";
  warning.className = "runtime-version-drift-warning";
  warning.setAttribute("role", "img");
  warning.setAttribute("aria-live", "polite");
  warning.textContent = "⚠️";
  warning.hidden = true;
  versionNode.insertAdjacentElement("afterend", warning);
  return warning;
}

export async function installRuntimeVersionDriftWarning() {
  const runtime = document.getElementById("runtime-topology");
  if (runtime?.dataset?.runtimeMode !== "homelab") return;

  const versionNode = document.querySelector(".hero .subtitle strong");
  if (!versionNode) return;
  const warning = ensureWarning(versionNode);
  const localVersion = versionNode.textContent?.trim() || "";

  try {
    const response = await fetch(FASTAPI_CLOUD_VERSION_URL, {
      cache: "no-store",
      headers: { Accept: "application/json", "Cache-Control": "no-cache" },
    });
    if (!response.ok) return;
    const payload = await response.json();
    const cloudVersion = String(payload?.version || "").trim();
    if (compareVersions(localVersion, cloudVersion) !== -1) {
      warning.hidden = true;
      return;
    }

    const message = `Local service version ${localVersion} is behind FastAPI Cloud ${cloudVersion}. Update the TrueNAS service.`;
    warning.hidden = false;
    warning.title = message;
    warning.setAttribute("aria-label", message);
  } catch {
    // Version drift is advisory only. Do not degrade application health if the
    // external FastAPI Cloud version cannot be observed from the local browser.
  }
}

export { compareVersions };
