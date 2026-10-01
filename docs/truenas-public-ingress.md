# TrueNAS public ingress diagnostics

Use this runbook to diagnose the public FastAPI Cloud → TrueNAS observation path
without weakening TLS or guessing which security layer blocked traffic.

Dated incident evidence is kept in [incidents.md](incidents.md).

## Intended path

```text
FastAPI Cloud
  -> HTTPS/WSS truenas.albandrieu.com:7000
  -> pfSense WAN / homelab public endpoint
  -> HAProxy :7000
  -> TLS re-encryption
  -> TrueNAS 172.17.0.24:7000
```

The current WAN address can be overridden with `HOMELAB_WAN_IPV4` and
`HOMELAB_WAN_PROVIDER`; do not encode an ISP address as immutable application
identity.

## Cloud source identity is observational

FastAPI Cloud egress addresses can rotate. Treat a captured source IP as
short-lived diagnostic evidence, never as a permanent allowlist contract.

Correlate several signals before attributing a source:

1. a synchronized FastAPI request;
2. pfSense state/capture for the same timestamp;
3. RDAP/WHOIS and ASN ownership;
4. PTR/provider prefix metadata only as supporting evidence.

Useful operator commands:

```sh
whois <observed-egress-ip>
host <observed-egress-ip>

tcpdump -nnvi mvneta0.4090   'host <observed-egress-ip> and tcp port 7000'
```

FastAPI may expose a bounded/cached observed public egress IP. That value is
informational only and must never rewrite firewall aliases, suppressions or pass
rules.

## Diagnose in protocol order

The platform pipeline is:

```text
DNS -> TCP connect -> TLS handshake -> HTTPS -> WebSocket -> Authentication -> API
```

Do not skip layers.

A successful TCP handshake is:

```text
source -> WAN:7000  SYN
WAN:7000 -> source  SYN,ACK
source -> WAN:7000  ACK
```

Repeated SYN with no SYN/ACK or RST means traffic is being silently dropped or
lost **before TLS**. Certificate settings cannot fix that state.

When TCP succeeds, inspect TLS separately. Keep
`TRUENAS_API_VERIFY_SSL=true` for the public HAProxy path.

The observer separates the logical TLS hostname from the socket destination:

- cloud runtime: connect directly to `HOMELAB_WAN_IPV4:7000` while sending
  SNI/hostname `truenas.albandrieu.com`; this bypasses DNS and isolates
  pfSense/HAProxy/TLS;
- homelab runtime: connect directly to
  `TRUENAS_LAN_HOST:TRUENAS_LAN_PORT` (defaults
  `172.17.0.24:7000`) with the same hostname SNI;
- the normal HTTP/API probe keeps the configured hostname URL.

Cloudflare Tunnel is not on either TrueNAS `:7000` path. Its state is
observational evidence for other tunneled services and must not decide TrueNAS
appliance liveness.

A raw-socket TLS timeout is auxiliary evidence. If the authenticated TrueNAS API
succeeds at the same time, the raw-socket failure is downgraded to a warning
because cloud runtimes may route raw sockets and application HTTPS differently.

The TLS diagnostic
requires TLS 1.2+ and may expose only non-secret metadata such as version, cipher,
certificate subject/issuer and expiry.

A TCP failure must be reported as `failure_stage=tcp_connect`, not as a TLS
timeout.

## Filtering evidence

Possible enforcement layers include PF, Snort, pfBlockerNG and CrowdSec.
A service being `running` proves only that the component is running.

For Snort/PF attribution, compare the synchronized observed source with:

```text
GET /api/v2/diagnostics/table?id=snort2c
```

Only an exact membership match is proven block evidence. If the API/table cannot
be queried, report attribution as unavailable/unknown rather than clear or
blocked.

The observer is read-only and requires no diagnostics-table DELETE privilege.

### Known Snort recurrence signature

The 2026-09-02 incident was caused by TLS on TCP 7000 being inspected as
clear-text HTTP. Recognition evidence included Snort `120:3` / `120:18`,
exact `snort2c` membership and WAN SYN packets without SYN/ACK.

Do not permanently allowlist the observed cloud IP. Correct the protocol
classification instead:

- TCP 7000 must not be in Snort HTTP Inspect clear-text server ports;
- use the TLS/SSL preprocessor only when appropriate and supported;
- do not hand-edit generated `snort.conf`;
- do not globally suppress all GID 120 events;
- keep `Block Offenders`/state killing only after the false-positive path is
  corrected and validated.

Full causal evidence:
[incident register](incidents.md#2026-09-02--fastapi-cloud-ingress-blocked-by-snort).

## pfBlockerNG and CrowdSec

For pfBlockerNG, distinguish IP-feed/PF blocking from DNSBL. Whitelisting the
FastAPI hostname in DNSBL does not permit an inbound source IP through a PF/IP
block rule.

Do not suppress an entire cloud allocation. Add a permanent source exception only
when the hosting platform provides a stable identity contract.

For CrowdSec, check for an active decision first:

```sh
cscli decisions list --ip <observed-egress-ip>
```

Do not create a permanent AllowList for a rotating cloud source.

## Isolate one enforcement engine at a time

A recurrence test should change one component only:

1. identify the current source with a synchronized capture;
2. record current `snort2c`, PF and security-engine state;
3. trigger one uncached health refresh;
4. inspect the same source immediately in `snort2c`, Snort alerts, WAN capture
   and `pflog0`;
5. alter only the suspected engine/rule;
6. repeat the identical probe and compare.

Restarting Snort, pfBlockerNG and CrowdSec together destroys attribution.

## Useful pfSense commands

```sh
# Exact Snort table membership
pfctl -t snort2c -T test <observed-egress-ip>

# Generated PF rules and counters
pfctl -sr -vv | grep -B4 -A8 snort2c

# Public TrueNAS flow
tcpdump -nnvi mvneta0.4090   'host <observed-egress-ip> and tcp port 7000'

# Logged PF decisions
tcpdump -nnevi pflog0   'host <observed-egress-ip> and tcp port 7000'

# HAProxy TrueNAS frontend/backend rows
echo "show stat" | socat stdio /tmp/haproxy.socket |   grep -E '^(#|freenas,|freenas_ipvANY,)'
```

Healthy HAProxy backend status is useful evidence for the HAProxy→TrueNAS leg; it
does not prove WAN PF/Snort/pfBlocker/CrowdSec accepted the source.

## Acceptance

A public ingress diagnosis is complete only when it identifies the first failing
layer and has independent evidence for that attribution.

For recovery, require:

- TCP SYN/SYN-ACK/ACK when the path should be accepted;
- verified TLS when TCP succeeds;
- no exact unintended `snort2c` membership for the current source;
- no recurrence of the known HTTP-Inspect-on-TLS signature;
- healthy HAProxy→TrueNAS backend evidence;
- no permanent allowlist created from transient cloud egress.
