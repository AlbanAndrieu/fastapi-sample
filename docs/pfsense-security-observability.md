# pfSense security observability plan

The FastAPI homelab observer should use the pfSense REST API as a **read-only
control-plane source**, complementing `/sickz` Internet-vantage probes. The two
signals answer different questions:

- `/sickz`: what is actually reachable from this runtime/vantage point?
- pfSense API: what firewall, NAT, gateway, interface and service policy is
  configured or currently observed on the firewall?

The API credentials must belong to dedicated read-only accounts. Do not grant
write, apply, reboot, command-prompt or configuration mutation privileges to the
FastAPI observer.

## Probe transport and credential split

The Snort block-attribution credential is intentionally narrower than the
posture credential:

```text
PFSENSE_API_URL=https://<pfSense-shared-endpoint>
PFSENSE_API_VERIFY_SSL=true

PFSENSE_SECURITY_API_KEY=<GET-diagnostics-table-only-key>
PFSENSE_SECURITY_API_URL=https://<pfSense-security-endpoint>  # optional; falls back to PFSENSE_API_URL
PFSENSE_SECURITY_API_VERIFY_SSL=true                          # optional
PFSENSE_SECURITY_PATH_MODE=shared_wan

PFSENSE_POSTURE_API_KEY=<broader-read-only-posture-key>
PFSENSE_POSTURE_API_URL=https://<pfSense-posture-endpoint>    # optional; falls back to PFSENSE_API_URL
PFSENSE_POSTURE_API_VERIFY_SSL=true                           # optional
```

`PFSENSE_SECURITY_API_KEY` needs exactly the pfSense privilege
`api-v2-diagnostics-table-get`, whose generated GUI name is
`REST API - /api/v2/diagnostics/table GET`. It does **not** need the matching
DELETE privilege. Do not assign `page-all`, `WebCfg - All pages`, shell access,
or any write privilege.

The posture observer needs additional GET privileges for the endpoints it
actually reads, currently including system version, service status, DNS Resolver
settings and system DNS. `PFSENSE_POSTURE_API_KEY` exists so those broader read
permissions do not have to be added to the narrow Snort credential.

Recommended pfSense owners are `fastapi-pfsense-security` for the security key
and `fastapi-pfsense-posture` for the posture key. Keep both pfSense user objects
enabled: pfREST rejects API-key authentication when the key owner is marked
`This user cannot login`. API keys themselves cannot authenticate to the
webConfigurator or SSH, so harden these service accounts by withholding WebCfg,
admin-group and shell privileges rather than disabling the user object.

The production FastAPI Cloud environment completed the credential split on
2026-09-02 and no longer defines `PFSENSE_API_KEY`. Runtime code may temporarily
retain the historical shared-key path for migration/rollback compatibility, but
that fallback is not the target configuration and must only activate when the
legacy variable is explicitly present. Do not restore the generic key or merge
the posture and security privileges back into one credential.

Use `PFSENSE_API_VERIFY_SSL=false` only for an explicitly trusted endpoint whose
certificate is self-signed or issued by an untrusted internal CA. The dedicated
clients can override it independently with `PFSENSE_SECURITY_API_VERIFY_SSL` and
`PFSENSE_POSTURE_API_VERIFY_SSL`.

Keep the pfSense REST API globally in read-only mode during normal operation.
Temporarily disabling read-only mode to create or rotate a key is acceptable,
but re-enable it immediately afterwards; the runtime observers require GET only.

### Shared-WAN diagnostic blind spot

A pfSense REST call made from FastAPI Cloud to the public `:10443` listener is
not an independent control plane when Snort/PF filters that same source on WAN.
The generated `snort2c` rules block the source bidirectionally, so a source that
is blocked from `:7000` may also be unable to query `:10443` to discover that it
is present in `snort2c`.

Set:

```text
PFSENSE_SECURITY_PATH_MODE=shared_wan
```

while the security API URL traverses the same WAN filter. In this mode a timeout
or connection failure is exposed as a **self-diagnostic blind spot**, not as
proof that Snort did or did not block the request.

A genuinely independent implementation must use a path that does not traverse
the same WAN Snort/PF decision. The preferred future architecture is a small
homelab-side observer that reads pfSense over LAN and publishes only sanitized
security evidence through an outbound authenticated channel, for example a
Cloudflare Tunnel protected by service authentication. Do not expose the raw
pfSense administration API merely to remove this blind spot.

Only after an independent path is actually deployed should the application be
configured with:

```text
PFSENSE_SECURITY_PATH_MODE=out_of_band
```

`/sickz` intentionally does not use these verification switches. Its HTTP
reachability phase must still detect a host with an invalid certificate as
**reachable**, while a separate TLS-trust probe reports the certificate problem.

## P0/P1 read-only data

Start small and normalize only fields that support an explicit security or
availability policy.

### API liveness, system and service status

- `GET /api/v2/system/version`
  - cheap authenticated API/liveness signal;
  - reads pfSense version files without collecting live system metrics.
- `GET /api/v2/status/system`
  - detailed software/runtime and host resource status;
  - use on demand or behind a separate cache because the model collects live
    platform, BIOS, temperature, CPU/load, mbuf, memory, swap and filesystem
    data and can exceed a short liveness timeout.
- `GET /api/v2/status/services`
  - detect expected critical services that are stopped;
  - useful for DNS resolver, DHCP, VPN and monitoring service availability.

Do not mark the whole homelab red solely because an optional service is stopped.
Map each service to an explicit policy.

### Snort block attribution

Use only:

```text
GET /api/v2/diagnostics/table?id=snort2c
```

for direct Snort/PF block attribution. Compare the returned table with the
FastAPI runtime's bounded/cached observed egress IP. An exact match can be shown
as a proven Snort/PF block; a service merely being `running` cannot.

The observer never calls:

```text
DELETE /api/v2/diagnostics/table
```

and never adds, removes or flushes table entries.

### Interfaces and gateways

- `GET /api/v2/status/interfaces`
  - link state;
  - addresses;
  - traffic/error counters when exposed by the model.
- `GET /api/v2/status/gateways`
  - default/WAN gateway state;
  - monitor state, RTT and packet loss where exposed.

These are useful to distinguish application failures from WAN/link problems and
to correlate future `e6000sw0port2` flaps or `dpinger` degradation.

### Firewall rules and aliases

- `GET /api/v2/firewall/rules`
- `GET /api/v2/firewall/aliases`

Use these to implement policy assertions, not to dump raw configuration into a
public health endpoint.

Target assertions include:

- no broad WAN `pass tcp any -> any` / Easy Rule;
- pfSense admin/API `10443/tcp` follows the source-aware `trusted_sources_only`
  policy. Approved stable administration sources may reach it, while unrelated
  Internet origins are denied. FastAPI Cloud direct reachability is diagnostic
  only until the platform provides a stable workload identity;
- TrueNAS SSH `9922/tcp` and firewall SSH `22/tcp` remain externally blocked;
- TrueNAS/HAProxy `7000/tcp` follows the same reviewed source-aware exception
  while FastAPI Cloud lacks a stable user-controlled egress identity.

Return only normalized compliance evidence such as rule identifiers,
descriptions, interface, protocol, source class, destination port and
pass/block intent. Do not expose unrelated internal addresses or full alias
contents through public endpoints.

### NAT

- `GET /api/v2/firewall/nat/port_forwards`

Validate that management ports are not accidentally exposed by NAT and that
direct HAProxy publication is not confused with a port forward. The expected
TrueNAS architecture is:

```text
Internet -> pfSense WAN:7000 -> HAProxy -> TLS re-encryption -> TrueNAS 172.17.0.24:7000
```

HAProxy runs in HTTP mode for this listener and preserves a valid WebSocket
upgrade natively; the application must not assume manually injected `Upgrade`
headers are required. The TrueNAS Platform pipeline therefore displays HAProxy
before the measured WebSocket upgrade and API authentication stages.

If HAProxy owns WAN:7000, a separate NAT port-forward for the same service is
unexpected configuration drift.

### DNS resolver policy

- `GET /api/v2/services/dns_resolver/settings`
- host override endpoints only when needed for policy validation.

Use this to support the planned DNS architecture review:

```text
LAN clients -> pfSense/Unbound -> filtering/upstream policy
  -> Pi-hole / AdGuard Home as explicitly designed
```

The goal is to preserve DNS resolution when TrueNAS Apps are down while still
making filtering behavior deterministic and auditable.

### VPN and remote administration

Where the relevant VPN is actually used:

- `GET /api/v2/status/openvpn/clients`
- `GET /api/v2/status/openvpn/servers`
- `GET /api/v2/status/wireguard/tunnels`
- `GET /api/v2/status/wireguard/peers`
- `GET /api/v2/services/ssh`

Use these to prove that remote administration uses the intended trusted path
rather than a public management listener.

### Logs

Useful bounded diagnostic endpoints include:

- `GET /api/v2/status/logs/firewall`
- `GET /api/v2/status/logs/system`
- `GET /api/v2/status/logs/auth`
- `GET /api/v2/status/logs/packages/restapi`

Logs may contain source addresses, usernames and other sensitive operational
metadata. They should be queried only for bounded troubleshooting windows and
must never be copied wholesale into `/healthz`, `/sickz`, browser JavaScript, or
public telemetry.

### DHCP/ARP inventory

- `GET /api/v2/status/dhcp_server/leases`
- `GET /api/v2/diagnostics/arp_table`

These can reconcile known infrastructure addresses and detect unexpected
devices, but they contain device/network identity data. Keep them out of public
responses and use them only for explicit inventory/security checks.

## API output target

Expose a small sanitized posture block rather than the raw pfSense response:

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

Each field should include evidence age and an internal diagnostic reason, while
public projections remain redacted.

## Implementation order

1. Keep the dedicated `snort2c` observer GET-only and separate from posture
  credentials.
2. Replace the shared-WAN `:10443` security control path with a sanitized
  out-of-band observer before treating telemetry failure as authoritative.
3. Add interfaces + gateways.
4. Add firewall rules + aliases and implement the Easy Rule/management-port
  policy assertions.
5. Add NAT checks.
6. Add DNS resolver policy.
7. Add VPN/service state only for services intentionally managed by the homelab.
8. Add bounded log correlation as a troubleshooting feature, not a continuous
  public health payload.
