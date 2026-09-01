# pfSense security observability plan

The FastAPI homelab observer should use the pfSense REST API as a **read-only
control-plane source**, complementing `/sickz` Internet-vantage probes. The two
signals answer different questions:

- `/sickz`: what is actually reachable from this runtime/vantage point?
- pfSense API: what firewall, NAT, gateway, interface and service policy is
  configured or currently observed on the firewall?

The API key must belong to a dedicated read-only account. Do not grant write,
apply, reboot, command-prompt or configuration mutation privileges to the
FastAPI observer.

## Probe transport

Canonical variables:

```text
PFSENSE_API_URL=https://<trusted-pfsense-endpoint>
PFSENSE_API_KEY=<read-only-api-key>
PFSENSE_API_VERIFY_SSL=true
```

Use `PFSENSE_API_VERIFY_SSL=false` only for an explicitly trusted private
endpoint whose certificate is self-signed or issued by an untrusted internal
CA. This setting applies to the pfSense API client only.

`/sickz` intentionally does not use this setting. Its HTTP reachability phase
must still detect a host with an invalid certificate as **reachable**, while a
separate TLS-trust probe reports the certificate problem. A generic
`SICKZ_ALLOW_INSECURE_CERT` switch is therefore unnecessary and would blur
reachability with certificate policy.

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
- pfSense admin `10443/tcp` is not permitted from arbitrary WAN sources;
- TrueNAS SSH `9922/tcp` and firewall SSH `22/tcp` remain externally blocked;
- TrueNAS/HAProxy `7000/tcp` is permitted only from approved source aliases once
  the temporary broad Easy Rule is removed;
- aliases such as `FASTAPI_CLOUD_EGRESS` and `TRUSTED_WORK_EGRESS` exist and are
  the sources used by the `7000/tcp` rule.

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
Internet -> pfSense WAN:7000 -> HAProxy -> TrueNAS 172.17.0.24:7000
```

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
  "elapsed_ms": 142,
  "gateway_state": "online",
  "wan_link_state": "up",
  "policy": {
    "broad_wan_pass_rule": false,
    "pfsense_admin_public": false,
    "truenas_ssh_public": false,
    "truenas_7000_source_restricted": true
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

1. Use `/api/v2/system/version` as the cheap liveness probe and instrument its
  latency/error stage; keep `/api/v2/status/system` out of the synchronous
  liveness path.
2. Add interfaces + gateways.
3. Add firewall rules + aliases and implement the Easy Rule/management-port
  policy assertions.
4. Add NAT checks.
5. Add DNS resolver policy.
6. Add VPN/service state only for services intentionally managed by the homelab.
7. Add bounded log correlation as a troubleshooting feature, not a continuous
  public health payload.
