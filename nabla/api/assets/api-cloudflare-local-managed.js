const REMOTE_INVENTORY_MESSAGE =
  "Cloudflare edge headers are present, but the hostname is absent from Tunnel ingress inventory.";
const LOCAL_MANAGED_MESSAGE =
  "Cloudflare edge headers are present. One or more Cloudflare Tunnels are local-managed, so per-host ingress cannot be verified through the remote Cloudflare API.";

function localManagedCount(summary) {
  const value = Number(summary?.local_managed_tunnels || 0);
  return Number.isFinite(value) ? value : 0;
}

function apply(summary) {
  if (localManagedCount(summary) <= 0) return;
  for (const detail of document.querySelectorAll(
    "#sickz-checks .health-row-detail",
  )) {
    const text = String(detail.textContent || "");
    if (!text.includes(REMOTE_INVENTORY_MESSAGE)) continue;
    detail.textContent = text.replace(
      REMOTE_INVENTORY_MESSAGE,
      LOCAL_MANAGED_MESSAGE,
    );
  }
}

export function decorateLocalManagedTunnelWording(summary) {
  window.setTimeout(() => window.requestAnimationFrame(() => apply(summary)), 0);
}
