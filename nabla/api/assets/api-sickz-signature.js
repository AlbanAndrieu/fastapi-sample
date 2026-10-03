export function sickzRowsSignature(checks) {
  return JSON.stringify(
    Object.keys(checks)
      .sort()
      .map((key) => {
        const check = checks[key] || {};
        const aliases = Object.entries(check.alias_results || {})
          .sort(([left], [right]) => left.localeCompare(right))
          .map(([url, value]) => [
            url,
            value?.reachable,
            value?.http_status,
            value?.error_kind,
            value?.error,
          ]);
        return [
          key,
          check.name,
          check.display_label,
          check.policy_status,
          check.policy_detail,
          check.reachable,
          check.http_status,
          check.skipped,
          check.reason,
          check.error_kind,
          check.error,
          check.external,
          check.tunnel_secure,
          check.cloudflare_tunnel_observed,
          check.cloudflare_default_deny,
          check.cloudflare_service_auth_attempted,
          check.cloudflare_service_token_access_passed,
          check.cloudflare_access_policy_count,
          check.tls_trusted,
          aliases,
        ];
      }),
  );
}

