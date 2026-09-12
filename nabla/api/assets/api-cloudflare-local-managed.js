const REMOTE_INVENTORY_MESSAGE =
  "Cloudflare edge headers are present, but the hostname is absent from Tunnel ingress inventory.";
const REMOTE_BADGE_MESSAGE =
  "Cloudflare edge traffic is observed, but the hostname is absent from the Tunnel ingress inventory. Check remote/local-managed tunnel configuration.";
const LOCAL_MANAGED_MESSAGE =
  "Cloudflare edge headers are present. One or more Cloudflare Tunnels are local-managed, so per-host ingress cannot be verified through the remote Cloudflare API.";

function localManagedCount(summary) {
  const value = Number(summary?.local_managed_tunnels || 0);
  return Number.isFinite(value) ? value : 0;
}

function replaceLocalManagedWording(value) {
  return String(value || "")
    .replace(REMOTE_INVENTORY_MESSAGE, LOCAL_MANAGED_MESSAGE)
    .replace(REMOTE_BADGE_MESSAGE, LOCAL_MANAGED_MESSAGE);
}

function apply(summary) {
  if (localManagedCount(summary) <= 0) return;
  for (const row of document.querySelectorAll("#sickz-checks .health-row")) {
    const detail = row.querySelector(".health-row-detail");
    if (detail) detail.textContent = replaceLocalManagedWording(detail.textContent);

    for (const badge of row.querySelectorAll(
      ".cloudflare-tunnel-badge, .service-probe",
    )) {
      const title = replaceLocalManagedWording(badge.title);
      if (title !== badge.title) badge.title = title;
      const aria = badge.getAttribute("aria-label");
      if (aria) badge.setAttribute("aria-label", replaceLocalManagedWording(aria));
    }
  }
}

export function decorateLocalManagedTunnelWording(summary) {
  window.setTimeout(() => window.requestAnimationFrame(() => apply(summary)), 0);
}
