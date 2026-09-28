# pfSense security observer contract

FastAPI uses the pfSense REST API as a **read-only control-plane source**. This
complements runtime reachability probes:

- `/sickz` answers what is reachable from the current runtime/vantage point;
- pfSense API evidence answers what policy/state the firewall reports.

Open implementation work belongs in
[engineering-roadmap.md](engineering-roadmap.md); dated failures belong in
[incidents.md](incidents.md).

## Credential and transport split

Keep the narrow block-attribution identity separate from broader posture reads:

```text
PFSENSE_API_URL=https://<pfSense-shared-endpoint>
PFSENSE_API_VERIFY_SSL=true

PFSENSE_SECURITY_API_KEY=<diagnostics-table-get-only-key>
PFSENSE_SECURITY_API_URL=https://<security-endpoint>   # optional
PFSENSE_SECURITY_API_VERIFY_SSL=true                   # optional
PFSENSE_SECURITY_PATH_MODE=shared_wan

PFSENSE_POSTURE_API_KEY=<broader-read-only-posture-key>
PFSENSE_POSTURE_API_URL=https://<posture-endpoint>     # optional
PFSENSE_POSTURE_API_VERIFY_SSL=true                    # optional
```

The security identity needs only
`api-v2-diagnostics-table-get` for
`GET /api/v2/diagnostics/table`. It never needs DELETE/table mutation,
WebCfg-all, shell, reboot or configuration-write privileges.

The posture identity receives only GET privileges for endpoints actually used,
such as system version, service status and DNS policy. Do not merge both
identities back into one broad key.

pfREST API key owners must remain enabled user objects. Harden them by withholding
interactive WebCfg/admin/shell privileges rather than disabling the user.

Keep the REST API globally read-only during normal operation. Temporarily
disabling read-only mode for key rotation is acceptable only for the rotation
window.

TLS verification stays enabled. An explicit internal/self-signed endpoint may
override verification independently for the security/posture client, but this
must not affect `/sickz` transport-vs-TLS evidence semantics.

## Shared-WAN blind spot

When FastAPI Cloud queries the public pfSense `:10443` path through the same WAN
PF/Snort policy being diagnosed, failure to reach that API is **not independent
evidence**.

Use:

```text
PFSENSE_SECURITY_PATH_MODE=shared_wan
```

A timeout in this mode means the security observer may be inside the same failure
domain. It does not prove that Snort did or did not block the source.

The durable target is a LAN-side observer that reads pfSense locally and
publishes only sanitized evidence through an outbound authenticated path. Set
`out_of_band` only after such an independent path actually exists. Never expose
the raw administration API merely to remove the blind spot.

## Read-only endpoint map

| Purpose | Endpoint | Use |
| --- | --- | --- |
| cheap authenticated control-plane check | `GET /api/v2/system/version` | normal API liveness |
| deep host/runtime state | `GET /api/v2/status/system` | on demand / separately cached |
| expected services | `GET /api/v2/status/services` | service policy evidence |
| Snort/PF attribution | `GET /api/v2/diagnostics/table?id=snort2c` | exact source membership |
| interfaces | `GET /api/v2/status/interfaces` | link/address/error context |
| gateways | `GET /api/v2/status/gateways` | WAN/monitor/RTT/loss context |
| firewall policy | `GET /api/v2/firewall/rules` | normalized policy assertions |
| aliases | `GET /api/v2/firewall/aliases` | source/destination policy classes |
| NAT | `GET /api/v2/firewall/nat/port_forwards` | unexpected management exposure |
| DNS policy | `GET /api/v2/services/dns_resolver/settings` | resolver resilience |
| bounded troubleshooting | status firewall/system/auth/REST logs | incident windows only |
| inventory | DHCP leases / ARP table | private explicit checks only |

VPN/SSH status endpoints should be queried only when those services are
intentionally part of the managed homelab.

Never use `GET /api/v2/status/system` as the synchronous lightweight liveness
probe; it collects substantially more live platform data.

## Snort attribution

Only an **exact source IP match** in `snort2c` is proof of table membership:

```text
GET /api/v2/diagnostics/table?id=snort2c
```

The observer never calls DELETE and never adds/removes/flushes PF table entries.

A running Snort service is not proof that Snort blocked a request. Conversely,
failure to query `snort2c` over a shared-WAN path is not proof that the table is
clear.

The known TLS-7000 false-positive incident signature is documented in
[incidents.md](incidents.md#2026-09-02--fastapi-cloud-ingress-blocked-by-snort).

## Policy assertions

Expose normalized assertions rather than raw configuration. Relevant policies
include:

- no broad WAN Easy Rule such as unrestricted TCP any→any;
- pfSense admin/API TCP 10443 follows reviewed trusted-source policy;
- TrueNAS SSH TCP 9922 and firewall SSH TCP 22 stay externally blocked;
- direct HAProxy TCP 7000 follows its reviewed source-aware exception;
- management ports are not accidentally exposed through NAT;
- DNS remains available when TrueNAS Apps are unavailable.

The expected direct HAProxy path is:

```text
Internet -> pfSense WAN:7000 -> HAProxy -> TLS re-encryption
         -> TrueNAS 172.17.0.24:7000
```

If HAProxy owns WAN 7000, a second NAT port-forward for the same service is
configuration drift.

## Public output and privacy

Return a small sanitized posture model, for example:

```json
{
  "reachable": true,
  "gateway_state": "online",
  "wan_link_state": "up",
  "ingress_block": {
    "state": "clear",
    "mechanism": "snort2c",
    "control_path": {
      "mode": "shared_wan",
      "blind_spot": true
    }
  },
  "dns": {
    "resolver_enabled": true,
    "policy_state": "ok"
  }
}
```

Preserve evidence age and detailed reasons internally. Do not publish raw aliases,
DHCP/ARP inventories, full firewall rules, usernames or log payloads.

Logs are incident evidence only: query bounded windows and never copy them
wholesale into `/healthz`, `/sickz`, browser JavaScript or public telemetry.

## Safety invariants

- GET-only operational identity;
- no automatic firewall/NAT/table mutation;
- no public raw pfSense payload;
- no assumption that shared-WAN telemetry is independent;
- no global homelab DOWN solely because an optional pfSense service is stopped;
- no weakening TLS/authentication to make diagnostics green.
