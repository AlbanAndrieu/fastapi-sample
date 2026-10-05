# pfSense security observer contract

FastAPI uses the pfSense REST API as a **read-only control-plane source**. This
complements runtime reachability probes:

- `/sickz` answers what is reachable from the current runtime/vantage point;
- pfSense API evidence answers what policy/state the firewall reports.

Open implementation work belongs in
[engineering-roadmap.md](engineering-roadmap.md); dated failures belong in
[incidents.md](incidents.md).

## pfSense source of authority and appliance limits

This repository owns the **FastAPI observer contract**, not the complete pfSense
host configuration. Before changing pfSense probe rate, concurrency, endpoint
depth, timeout policy or interpreting a control-plane slowdown, consult the
current pfSense documentation in `AlbanAndrieu/nabla-compose`.

Canonical cross-repository references:

- `docs/pfsense-php-fpm-hardening.md` — PHP-FPM sizing, FastCGI backlog,
  restart/recovery contract and post-upgrade reconciliation;
- `docs/pfsense-flow-observability-memory.md` — Netgate 1100 memory budget,
  Snort/pfBlockerNG/Unbound constraints and observability offload;
- `docs/pfsense-diagnose-recover.md` — bounded diagnostic/recovery sequence;
- `.agents/skills/pfsense-api-debugging/SKILL.md` — current portable pfSense
  operational contract.

The currently documented appliance is a Netgate 1100 with roughly 1 GiB RAM
and no swap. Historical evidence includes PHP-FPM workers around 48–65 MiB RSS,
FastCGI socket listen-queue overflow and kernel memory-reclaim/OOM events.
The reviewed Nabla constrained PHP-FPM profile is `max_children=4`,
`start_servers=1`, `max_spare_servers=2`, `process_idle_timeout=30` and
`max_requests=500`.

Those values are host/runtime facts and may change after a pfSense upgrade.
`nabla-compose` is the source to revalidate them; do not duplicate or silently
override that host policy from FastAPI Sample.

### Current latency interpretation

The 2026-10-04 LAN measurements showed sub-millisecond TCP establishment and
roughly 17–27 ms TLS setup while pfREST time-to-first-byte varied from about
0.86 s to 3.46 s. Packet capture showed normal bidirectional TCP/TLS exchange
without observed kernel packet loss. That evidence localizes most delay after
TLS, inside or behind the pfSense HTTP/pfREST control plane.

Given the previously documented FastCGI backlog and memory pressure, the leading
hypothesis is PHP-FPM/pfREST queueing or resource saturation, potentially
amplified by repeated failed KeyAuth/Login Protection work. This is a capacity
hypothesis, not a proven root cause. Confirm it with fresh post-reboot
PHP-FPM-worker, `vmstat`, socket/listen-queue and timestamped log evidence
before changing the Nabla PHP-FPM limits.

FastAPI Sample therefore protects the appliance instead of increasing probe
pressure:

- one authenticated `GET /api/v2/system/version` preflight;
- fail fast on HTTP 401;
- skip deep posture fan-out when that authenticated preflight takes at least
  2.5 s;
- keep the 2.5 s threshold provisional until correlated p95/p99 and appliance
  saturation evidence is available.

### Probe provenance and trace correlation

Outbound pfSense requests add diagnostic metadata only; these headers never
participate in KeyAuth, authorization or health-state decisions:

```text
Nabla-Probe: pfsense-posture | pfsense-security | pfsense-*-auth-smoke
Nabla-Probe-Source: fastapi-cloud | truenas | workstation | unknown
traceparent: W3C Trace Context
tracestate: optional, only when inherited from an active OTel context
```

Do not use `X-Nabla-*`; application-specific fields use descriptive Nabla
names. `Nabla-Probe-Source` is deliberately bounded and low-cardinality.
When an active OpenTelemetry context exists, the W3C trace context is propagated;
otherwise the observer creates a valid standalone unsampled `traceparent`.
The implementation deliberately does **not** propagate OpenTelemetry baggage.

Capture these fields only in bounded diagnostic logs where useful. Never use
`traceparent` or a trace/span identifier as a Prometheus label, cache key,
circuit-breaker key or health-card dimension.

For the direct TrueNAS-to-pfSense control path on TCP 10443, nginx/pfREST on
pfSense is the relevant receiving layer; HAProxy is not in that datapath. For
the public TrueNAS TCP 7000 path, HAProxy can participate in correlation after
TLS termination. Any persistent pfSense/nginx/HAProxy logging customization
belongs in `nabla-compose` and must respect the Netgate 1100 resource budget.

### Cloud versus TrueNAS authenticated observation

FastAPI Cloud is an external/WAN observer and must keep
`PFSENSE_AUTHENTICATED_PROBES_ENABLED=false`. TrueNAS/homelab is the
authoritative authenticated LAN observer.

The FastAPI Cloud deployment workflow is intentionally declarative for this
setting. Even if the remote FastAPI Cloud environment was already manually set
to `false`, a workflow command setting the variable to `true` would overwrite
that remote value during the next deployment. Keep the checked-in deploy
contract and the remote environment aligned rather than relying on manual drift.

## Validate deployed keys from the TrueNAS runtime

A workstation timeout before TCP/TLS does not validate or invalidate an API key.
To test the exact keys injected into the TrueNAS-hosted `fastapi-sample`
container while bypassing a broken public/hairpin path, run:

```bash
sudo docker exec fastapi-sample \
  /code/.venv/bin/python -m nabla.api.pfsense_auth_smoke \
  --url https://172.17.0.1:10443 \
  --insecure
```

The command never prints either key or a response body. Acceptance is the
least-privilege matrix:

| identity | endpoint family | expected |
| --- | --- | --- |
| posture | version, services, DNS resolver, system DNS | HTTP 200 |
| posture | `diagnostics/table?id=snort2c` | HTTP 403 |
| security | `diagnostics/table?id=snort2c` | HTTP 200 |
| security | `status/services` | HTTP 403 |

`transport_error` means the request never reached an HTTP authorization
decision and therefore says nothing about key validity. HTTP `401` proves the
transport reached pfSense but the supplied runtime key was not accepted.


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

### Post-upgrade API-key recovery

A pfSense/REST API package upgrade can leave previously deployed runtime keys
missing or invalid from the application's point of view. On 2026-10-04 the
homelab upgrade was followed by HTTP 401 from
`GET /api/v2/system/version` until the dedicated API keys were recreated.
Treat this as a credential-rotation/revalidation event after upgrades; do not
classify HTTP 401 as a network outage.

The canonical runtime uses exactly two independently rotatable keys.

Create two **local service users** in `System > User Manager`; do not reuse
`admin`, a personal administrator, or the `admins` group:

- `fastapi_posture`
- `fastapi_security`

pfSense requires a user to be saved before privileges can be assigned. Edit each
saved user and add only the REST API privileges below. Optionally add
`User - Config: Deny Config Write` as defense in depth. Do not grant
`WebCfg - All pages`, shell/SSH, reboot or configuration-write privileges.

pfREST API keys belong to the user that generates them. Generate each key while
authenticated as the corresponding service user. For a CLI rotation, temporarily allow `api-v2-auth-key-post` on that user.
`POST /api/v2/auth/key` forces BasicAuth independently of the global
authentication-method list. If REST API read-only mode is enabled, temporarily
disable it only for the key-creation window; if it is already disabled, no
settings change is required. Remove `api-v2-auth-key-post` immediately after
the key is captured. Keep the user enabled after
key creation because authorization is evaluated against that user's current
privileges.

| Runtime variable | Purpose | Minimum GET privileges |
| --- | --- | --- |
| `PFSENSE_POSTURE_API_KEY` | liveness, services and DNS posture | `api-v2-system-version-get`, `api-v2-status-services-get`, `api-v2-services-dns-resolver-settings-get`, `api-v2-system-dns-get` |
| `PFSENSE_SECURITY_API_KEY` | exact Snort/PF table attribution | `api-v2-diagnostics-table-get` |

The historical `PFSENSE_API_KEY` is no longer consumed by FastAPI Sample.
**Delete it from runtime secrets and do not recreate it.** Both dedicated clients
inherit `PFSENSE_API_URL` and `PFSENSE_API_VERIFY_SSL` unless a dedicated
URL/TLS override is explicitly required.

After any pfSense or REST API package upgrade:

1. verify API-key authentication is still enabled;
2. verify both service users remain enabled and retain only their GET privileges;
3. recreate/rotate the posture and security keys if they are absent or return
   HTTP 401;
4. verify the newly generated keys are actually present in
   `System > REST API > Keys` under the expected owner usernames;
5. update the runtime secret store without logging the key values;
6. redeploy/restart the observer and purge the provider cache/circuit state;
7. require HTTP 2xx from the posture endpoint and the diagnostics-table endpoint
   before declaring credential recovery complete.

### HTTP 401 after key rotation

When **every endpoint returns 401 for a newly generated key**, authorization is
not the problem yet. pfREST authenticates the raw `X-API-Key` value by hashing
it and comparing it with the stored key hashes before endpoint privileges are
checked. A privilege problem should therefore be diagnosed only after the key
authenticates; a valid but under-privileged identity is expected to reach the
authorization layer (typically HTTP 403).

Inspect the API configuration from the pfSense shell or with an already valid
administrator key. `auth_methods` must contain `KeyAuth` for normal
`X-API-Key` authentication.

A Basic-Auth request to an ordinary endpoint can still return HTTP 401 when
global `auth_methods` contains only `KeyAuth`; this does not prove that the
local user's password is wrong. The key-creation endpoint
`POST /api/v2/auth/key` is special: pfREST explicitly forces `BasicAuth` for
that endpoint even when BasicAuth is not globally enabled.

Then inventory the stored API keys:

```bash
curl -sS -u admin \
  -H 'Accept: application/json' \
  https://home.albandrieu.com:10443/api/v2/auth/keys |
jq '.data[] | {id, username, hash_algo, length_bytes, descr}'
```

The posture/security keys must appear with owners `fastapi_posture` and
`fastapi_security`, respectively. The real key is representation-only and is
not recoverable later; the API stores only its hash. A 24-byte generated key is
48 hexadecimal characters.

The key owner must also still exist and be enabled. pfREST first matches the
submitted key hash, then rejects authentication if the owning user is disabled.
From the pfSense shell, this checks the exact condition used by pfREST without
printing secrets:

```csh
php -r 'require_once "RESTAPI/autoloader.inc"; foreach (["fastapi_posture","fastapi_security"] as $u) { printf("%s enabled=%s\n", $u, \RESTAPI\Core\Auth::is_user_enabled($u) ? "yes" : "no"); }'
```

If `KeyAuth` is enabled, both key records exist under enabled expected users,
and the runtime still receives 401, revoke those two records and generate fresh
keys, copying the `data.key` value returned at creation exactly once. Do not
copy the stored hash, an ID, or a masked UI value.

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

For the TrueNAS-hosted observer, `out_of_band` is valid only when the security
request reaches a LAN-side pfSense address independently from the WAN/Snort path
being diagnosed. Verify the actual peer from the same runtime. If
`home.albandrieu.com:10443` resolves/connects to the public WAN address, the
mode remains `shared_wan`. A split-DNS/internal hostname resolving to the
pfSense LAN address can support `out_of_band` while retaining TLS hostname
verification. Prefer an explicit `PFSENSE_SECURITY_API_URL` for this path so
the assumption is visible in configuration.

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
