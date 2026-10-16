# Garage public-ingress audit

Use this runbook when a Garage hostname is marked `external=false` but answers from the public Internet. Do not paste complete Cloudflare Access `Location` headers into issues or chat: query parameters can contain short-lived signed metadata.

## 1. Confirm the catalog (Cloud API)

Set `API` explicitly; an unset or empty value causes curl's `URL rejected: No host part`.

```bash
export API="${API:-https://fastapi-sample.fastapicloud.dev}"
: "${DIAGNOSTICS_ACCESS_KEY:?Export DIAGNOSTICS_ACCESS_KEY first}"

curl -fsS --connect-timeout 5 --max-time 20 \
  -H "X-Diagnostics-Key: $DIAGNOSTICS_ACCESS_KEY" \
  "$API/api/homelab-services" |
jq '[.services[] | select((.id // "") | startswith("garage")) |
    {id, name, external, internalPort, tunnelUrl}]'
```

A catalogue value of `external=false` describes desired exposure; it does not prove that public DNS, Cloudflare Tunnel, HAProxy or NAT agrees.

## 2. Inspect public edge response without leaking Access tokens

```bash
for host in garage-admin.albandrieu.com s3.int.albandrieu.com garage.albandrieu.com; do
  printf '\n== %s ==\n' "$host"
  curl -sS -D - -o /dev/null --connect-timeout 5 --max-time 10 \
    "https://$host/" |
  awk 'BEGIN { IGNORECASE=1 }
    /^HTTP\// || /^server:/ || /^cf-ray:/ { print }
    /^location:/ { sub(/\?.*/, "?<redacted>", $0); print }'
done
```

Interpretation:
- A Cloudflare `302` to `*.cloudflareaccess.com/.../login/...` confirms a public edge/Access route is responding. It does not prove the origin is anonymously reachable or identify the origin port.
- `server: cloudflare` alone does not establish that the origin is Cloudflare Tunnel; confirm the configured route in Cloudflare Zero Trust.
- A response from the LAN to a hostname does not establish external reachability; use a device/network outside the LAN for outside-in validation.

## 3. Reconcile declared and actual routing

For each hostname, compare:
1. Catalog intent (`external`, `internalHost`, `internalPort`, `tunnelUrl`).
2. Public DNS (`dig +short CNAME <hostname>` and `dig +short A <hostname>`).
3. Cloudflare Zero Trust → Networks → Tunnels → the active tunnel → Public Hostnames / published application routes, including the configured origin URL and port.
4. pfSense HAProxy frontend/backend and NAT rules, then Traefik routers/services and their target ports.
5. Outside-in response and LAN response, recorded separately.

For `garage-admin.albandrieu.com`, a public Cloudflare Access login redirect was observed on 2026-10-15. This is a **publicly reachable Access gate**, not proof of anonymous origin access. Since Garage Admin API is intended to be private, remove its public hostname/tunnel ingress and any associated public DNS publication after verifying which configuration source owns them. Do not merely rely on Access as a substitute for the private-only policy.

Expected service ports on TrueNAS:
- Garage S3 API: `:3900`, private only.
- Garage Admin API: `:3903`, private only.
- Garage Web UI: `:3909`, temporarily public by explicit user decision, behind appropriate access control.

## 4. Record evidence precisely

Report each layer as `matched`, `drift`, or `unknown`. A missing credential/API response is `unknown`, not proof that no route exists. Never put Access `Location` query strings, API keys, or service tokens in logs or reports.

## 5. Offline preparation: machine-readable drift evidence

Generate a sanitized JSON report without requiring TrueNAS access. Each service
must keep *intent*, *observation* and *inference* separate.

Suggested record:

```json
{
  "service_id": "garage-admin",
  "expected_external": false,
  "origin_port": 3903,
  "layers": {
    "public_dns": {"status": "unknown", "evidence": null},
    "cloudflare_tunnel": {"status": "unknown", "evidence": null},
    "cloudflare_access": {"status": "observed", "http_status": 302},
    "pfsense_nat_haproxy": {"status": "unknown", "evidence": null},
    "traefik": {"status": "unknown", "evidence": null},
    "outside_in_origin": {"status": "unknown", "evidence": null}
  },
  "exposure_assessment": "requires_review",
  "origin_anonymously_accessible": null
}
```

**Rules for automation:**
- `unknown` is never converted into `matched` or `drift`.
- A public Access redirect on a private-intent hostname is an **edge route
  review finding**, not proof of an origin bypass.
- Report a confirmed policy drift only when an authoritative active route or
  outside-in observation demonstrates unwanted exposure; retain the evidence
  source, timestamp, and freshness.
- For a private API, even an authenticated public route should be flagged
  for removal review; authentication does not change `external=false`.
- Do not follow redirects to login endpoints or store signed `Location` query
  parameters, cookies, bearer tokens or Cloudflare service-token values.
- Make every probe bounded (timeout, concurrency and retries), passive by
  default, and avoid destructive or authenticated mutations.
- Reconcile against the `nabla-compose` catalog revision and record that
  revision explicitly; if unavailable, report `catalog_revision=unknown`.

## 6. Cross-repository probe priority migration contract

The source of authority is `nabla-compose/catalog/homelab-exposure-overrides.json`.
An optional integer `probePriority` expresses ascending priority; absence
means ordinary rotating eligibility. The three Garage entries should receive
ranks 0, 1 and 2. Do not infer priority from `criticality`, and do not enable
public probing for `external=false` services.

Acceptance sequence:
1. Publish the schema and catalog field in `nabla-compose`, with validation
   for integer types, uniqueness where required, and non-negative values.
2. Extend `HomelabService` with alias `probePriority` and propagate it from
   exposure overrides in `fastapi-sample`.
3. Use catalog priority in the sampler, keeping the current bootstrap ordering
   only when no published priority is present.
4. Assert Garage inclusion, fair rotation of unrelated services, stable
   `rotated_priority_ids`, and unchanged public/internal probe eligibility.
5. Run focused unit/contract tests and the full offline quality gate at the
   exact commit SHA before considering the PR ready.

No live Cloudflare, TrueNAS, pfSense, or Traefik changes are authorized by
this preparation. Keep the PR open and do not merge automatically.
