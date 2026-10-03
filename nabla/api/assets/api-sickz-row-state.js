import { shortHostForDetail } from "./api-health-ui.js";
import {
  hasReachableNon2xxHttp,
  isForbiddenOnlyReachable,
} from "./api-sickz-policy.js";

export function classifySick(check) {
  if (check.policy_status === "ok") return "green";
  if (check.policy_status === "warn") return "yellow";
  if (check.policy_status === "fail") return "yellow";
  if (check.policy_status === "unknown") return "gray";
  if (check.skipped === true) return "yellow";

  if (typeof check.expected_reachable === "boolean") {
    if (check.reachable == null) return "gray";
    if (check.reachable !== check.expected_reachable) {
      return check.expected_reachable ? "yellow" : "red";
    }
    if (check.tls_trusted === false) return "yellow";
    return "gray";
  }

  if (check.reachable === true) {
    if (isForbiddenOnlyReachable(check)) return "yellow";
    if (hasReachableNon2xxHttp(check)) return "blue";
    return "red";
  }
  return "gray";
}

function isTrueNasExposureCheck(check) {
  const name = String(check?.name || check?.display_label || "")
    .trim()
    .toLowerCase();
  const aliases = Array.isArray(check?.aliases_probed)
    ? check.aliases_probed
    : [];
  return (
    name === "truenas" ||
    aliases.some((url) => String(url).includes("truenas.albandrieu.com:7000"))
  );
}

function rawDetailSickText(check) {
  if (check.skipped === true) {
    const intro = isTrueNasExposureCheck(check)
      ? "HTTPS exposure check skipped on trusted LAN. This is not the authenticated TrueNAS API probe; see Core drill-down · TrueNAS platform + API."
      : check.reason || "Not probed (LAN skip).";
    if (check.aliases_probed?.length) {
      return `${intro} Targets: ${check.aliases_probed.map(shortHostForDetail).join(" · ")}`;
    }
    return intro;
  }
  if (check.alias_results && check.aliases_probed) {
    const bits = [];
    check.aliases_probed.forEach((url) => {
      const result = check.alias_results[url];
      const tail = shortHostForDetail(url);
      if (!result) return;
      if (result.reachable === true) {
        bits.push(
          `${tail} → reachable${result.http_status != null ? ` (HTTP ${result.http_status})` : ""}`,
        );
      } else if (result.error) {
        bits.push(`${tail} → unreachable (${result.error})`);
      } else {
        bits.push(`${tail} → unreachable`);
      }
    });
    const line = bits.join(" · ");
    if (isForbiddenOnlyReachable(check)) {
      return `${line} — HTTP 403 only: host responded but access is forbidden.`;
    }
    return line;
  }
  if (check.reachable === true) {
    const parts = ["Reachable."];
    if (check.http_status != null) parts.push(`HTTP ${check.http_status}`);
    return parts.join(" ");
  }
  if (check.reachable === false) {
    if (check.error) return `Unreachable. ${check.error}`;
    return "Unreachable.";
  }
  return "Unknown reachability state.";
}

export function detailSickText(check) {
  const raw = rawDetailSickText(check);
  if (isTrueNasExposureCheck(check) && check.tunnel_secure === false) {
    const fallback =
      typeof check.expected_reachable === "boolean"
        ? check.expected_reachable
          ? "Policy enrichment unavailable; endpoint is expected reachable from this external observer."
          : "Policy enrichment unavailable; endpoint is expected blocked from this external observer."
        : "Direct pfSense/HAProxy exposure policy is evaluated separately from TrueNAS appliance health.";
    const policy = check.policy_detail || fallback;
    return `Direct exposure policy only — ${policy} Probe evidence: ${raw}`;
  }
  if (
    !check.policy_status &&
    typeof check.expected_reachable === "boolean"
  ) {
    const expectation = check.expected_reachable
      ? "expected reachable from this external observer"
      : "expected blocked from this external observer";
    return `Policy enrichment unavailable · ${expectation}. Raw evidence: ${raw}`;
  }
  if (
    check.policy_status === "ok" &&
    check.external === false &&
    check.reachable === false
  ) {
    const policy =
      check.policy_detail ||
      "external=false and the endpoint is not reachable from the external probe.";
    return `Policy compliant private exposure — ${policy} Evidence: ${raw}`;
  }
  if (!check.policy_detail) return raw;
  const warning =
    ["warn", "fail"].includes(check.policy_status) &&
    !String(check.policy_detail).startsWith("⚠️")
      ? "⚠️ "
      : "";
  return `${raw} — ${warning}${check.policy_detail}`;
}

