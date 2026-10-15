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
