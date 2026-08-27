import { httpStatusIsSuccess2xx } from "./api-health-ui.js";

function reachableHttpStatuses(check) {
  if (check.alias_results && check.aliases_probed) {
    const out = [];
    check.aliases_probed.forEach((url) => {
      const result = check.alias_results[url];
      if (result && result.reachable === true && result.http_status != null) {
        out.push(result.http_status);
      }
    });
    return out;
  }
  if (check.reachable === true && check.http_status != null)
    return [check.http_status];
  return [];
}

export function isForbiddenOnlyReachable(check) {
  if (check.skipped === true || check.reachable !== true) return false;
  const statuses = reachableHttpStatuses(check);
  if (statuses.length === 0) return false;
  return statuses.every((status) => status === 403);
}

export function hasReachableNon2xxHttp(check) {
  if (check.skipped === true || check.reachable !== true) return false;
  if (isForbiddenOnlyReachable(check)) return false;
  const statuses = reachableHttpStatuses(check);
  if (statuses.length === 0) return false;
  return statuses.some((status) => !httpStatusIsSuccess2xx(status));
}

export function networkPhrase(data) {
  return data.network_label ? `"${data.network_label}"` : "this deployment";
}

export function tcpPolicyViolation(check) {
  const ports = check.pfsense_tcp_ports;
  const policy = check.pfsense_tcp_port_policy;
  if (!ports || !policy) return false;
  return Object.keys(policy).some((port) => {
    const expected = policy[port]?.expected_reachable;
    const actual = ports[port];
    return (
      typeof expected === "boolean" &&
      typeof actual === "boolean" &&
      expected !== actual
    );
  });
}
