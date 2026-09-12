import { dependencyDetailText } from "./api-health-dependency.js";

export function isExpectedSentryDebugFailure(key, check) {
  return (
    key === "sentry" &&
    check.reachable === true &&
    Number(check.http_status) === 500 &&
    (check.via === "/sentry-debug" || check.path === "/sentry-debug")
  );
}

function cloudflareDetailText(check) {
  const status = Number(check.http_status);
  if (check.api_reachable === true && check.status_confirmed === true) {
    const parts = [
      Number.isFinite(status)
        ? `Cloudflare API HTTP ${status}`
        : "Cloudflare API reachable",
    ];
    const total = Number(check.tunnel_count);
    const healthy = Number(check.healthy_tunnels);
    const inactive = Number(check.inactive_tunnels);
    const degradedOrDown = Number(check.degraded_or_down_tunnels);
    if (Number.isFinite(total) && Number.isFinite(healthy)) {
      parts.push(`${healthy}/${total} tunnels healthy`);
    }
    if (Number.isFinite(inactive) && inactive > 0) {
      parts.push(
        `${inactive} inactive tunnel${inactive === 1 ? "" : "s"} in inventory`,
      );
    }
    if (Number.isFinite(degradedOrDown) && degradedOrDown > 0) {
      parts.push(
        `${degradedOrDown} degraded/down tunnel${degradedOrDown === 1 ? "" : "s"}`,
      );
    }
    return parts.join(" · ");
  }
  if (check.api_reachable === true) {
    return [
      Number.isFinite(status)
        ? `Cloudflare API HTTP ${status}`
        : "Cloudflare API reachable",
      "control-plane inventory unconfirmed",
      check.error || check.warning || "read-only verification is incomplete",
    ]
      .filter(Boolean)
      .join(" · ");
  }
  if (check.api_reachable === false) {
    return [
      "Cloudflare API unavailable",
      "control-plane verification paused",
      check.error || check.warning,
    ]
      .filter(Boolean)
      .join(" · ");
  }
  return [
    "Cloudflare control-plane verification unavailable",
    check.error || check.warning,
  ]
    .filter(Boolean)
    .join(" · ");
}

function baseDetailText(key, check) {
  if (check.skipped)
    return check.reason || "Not configured (intentionally disabled).";
  if (key === "cloudflare") return cloudflareDetailText(check);
  if (check.warning) return String(check.warning);
  if (isExpectedSentryDebugFailure(key, check)) {
    return "HTTP 500 · Expected: the test error was intentionally triggered and captured by Sentry.";
  }
  if (key === "truenas_api" && check.reachable === true) {
    const parts = ["WebSocket API connected"];
    if (check.version) parts.push(String(check.version));
    if (check.app_count != null) parts.push(`${check.app_count} apps`);
    return parts.join(" · ");
  }
  if (check.reachable === true) {
    const parts = [];
    if (check.http_status != null) parts.push(`HTTP ${check.http_status}`);
    if (check.path) parts.push(check.path);
    if (check.host != null && check.port != null)
      parts.push(`${check.host}:${check.port}`);
    if (check.url) parts.push(String(check.url).replace(/^https?:\/\//i, ""));
    return parts.length ? parts.join(" · ") : "Connected.";
  }
  if (check.error_kind) {
    const stage = String(check.error_kind).replaceAll("_", " ");
    return check.error ? `${stage}: ${check.error}` : stage;
  }
  if (check.error) return check.error;
  return "Unreachable.";
}

function sourcePolicyDetailText(key, check) {
  if (
    key !== "pfsense" ||
    check?.ingress_policy?.state !== "possible_ingress_policy_block"
  )
    return "";
  const egress = Array.isArray(check.ingress_policy.active_egress_ips)
    ? check.ingress_policy.active_egress_ips.filter(Boolean).join(", ")
    : "";
  return [
    "possible pfSense ingress-policy block",
    egress ? `active cloud egress ${egress}` : "",
    "possible trusted-source drift or PF/Snort filtering",
    "direct WAN probe is diagnostic only",
    "prefer out-of-band observer",
  ]
    .filter(Boolean)
    .join(" · ");
}

export function detailText(key, check) {
  const details = [
    baseDetailText(key, check),
    sourcePolicyDetailText(key, check),
    dependencyDetailText(check),
  ].filter(Boolean);
  return details.join(" · ");
}
