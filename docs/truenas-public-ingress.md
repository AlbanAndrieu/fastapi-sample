# TrueNAS public ingress diagnostics

This document records the intended public path used by FastAPI Cloud to observe the TrueNAS API and explains how to diagnose security-engine blocks without weakening TLS.

## Intended path

```text
FastAPI Cloud replica
  |
  | outbound HTTPS / WSS
  v
truenas.albandrieu.com:7000
  |
  | DNS -> 82.66.4.247
  v
Free static IPv4: 82.66.4.247
  |
  v
pfSense WAN / HAProxy :7000
  |
  | TLS re-encryption
  v
TrueNAS 172.17.0.24:7000
```

`82.66.4.247` is the homelab static public IPv4 assigned by Free. The application exposes it as non-secret diagnostic metadata. The defaults may be overridden with `HOMELAB_WAN_IPV4` and `HOMELAB_WAN_PROVIDER` if the ISP or address changes.

## FastAPI Cloud source IPs

During the 2026-09-02 incident, a synchronized WAN capture showed requests from `52.1.10.241`. That address is part of Amazon infrastructure and was the effective source address observed for the running FastAPI Cloud replica at that moment.

Treat this as **observed egress**, not as a permanent FastAPI Cloud allowlist contract. Do not assume that another deployment, replica, region, or platform change will keep the same address. In particular, do not broadly allowlist the surrounding AWS range solely to make the health probe work.

A WAN capture for one refresh can be restricted to the observed source:

```sh
tcpdump -nnvi mvneta0.4090 'host 52.1.10.241 and tcp port 7000'
```

An accepted connection should contain the TCP three-way handshake:

```text
52.1.10.241:<ephemeral> -> 82.66.4.247:7000  SYN
82.66.4.247:7000        -> 52.1.10.241:<ephemeral>  SYN,ACK
52.1.10.241:<ephemeral> -> 82.66.4.247:7000  ACK
```

Repeated inbound `SYN` packets with no `SYN,ACK` or `RST` indicate a silent drop before TLS. TLS certificate settings cannot fix that condition.

## TCP and TLS are separate stages

The TrueNAS platform pipeline measures the following independently:

```text
DNS -> TCP connect -> TLS handshake -> HTTPS -> WebSocket -> Authentication -> API
```

The TCP connect and TLS handshake use the same socket. If the TCP connection fails, the TLS stage is reported as `blocked` with `failure_stage=tcp_connect`; it must not be reported as a TLS timeout because no ClientHello was exchanged.

When `TRUENAS_API_VERIFY_SSL=true` and the handshake succeeds, the TLS stage exposes non-secret certificate metadata such as:

- negotiated TLS version and cipher;
- certificate common name;
- issuer common name;
- certificate expiration timestamp and remaining days;
- whether certificate and hostname verification were enabled.

The public certificate observed on 2026-09-01 was `CN=*.albandrieu.com`, issued by Let's Encrypt `YR2`, matched `truenas.albandrieu.com`, and verified successfully. Keep `TRUENAS_API_VERIFY_SSL=true` for this public HAProxy endpoint.

## Snort / `snort2c`

Snort inserts blocked hosts into the PF table `snort2c`. The generated PF rules are `block drop log quick`, so they can execute before a later WAN Easy Rule.

Test the currently observed FastAPI Cloud source directly from the pfSense shell:

```sh
pfctl -t snort2c -T test 52.1.10.241
```

A `1/1 addresses match` result means the address is currently in the table. A `0/1` result after stopping Snort does not prove that the address was absent before the service/table was cleared.

For a confirmed false positive, prefer a Snort **Pass List** containing only the trusted external address/range and assign that list to the relevant Snort interface. Do not rely on a later generic PF pass rule to override a preceding `quick` Snort block.

## pfBlockerNG

First identify whether the block is an IP feed/alias block or DNSBL block. They are different mechanisms:

- an inbound FastAPI Cloud connection is filtered by its source IP, not by the hostname `fastapi-sample.fastapicloud.dev`;
- adding `fastapi-sample.fastapicloud.dev` to DNSBL whitelist does not allow `52.1.10.241` through an IP block rule;
- if an IP feed is responsible, suppress or whitelist the smallest confirmed external IP entry in that feed/alias rather than an entire AWS allocation.

Because FastAPI Cloud does not currently document a stable egress IP for this application, keep any temporary source-IP exception narrow and revalidate it after deployment changes.

## CrowdSec

Check for an active decision before adding an exception:

```sh
cscli decisions list --ip 52.1.10.241
```

If a stale decision exists, remove it:

```sh
cscli decisions delete --ip 52.1.10.241
```

For a genuinely stable and trusted source, CrowdSec's preferred IP/CIDR mechanism is an AllowList. Do not create a permanent FastAPI Cloud AllowList until the platform provides a stable egress contract or repeated observations demonstrate an operationally acceptable range.

## Isolate the blocking engine

If stopping pfBlockerNG, Snort, and CrowdSec restores the endpoint, re-enable them one at a time and run one uncached TrueNAS health refresh after each change:

1. enable pfBlockerNG only and validate;
2. enable CrowdSec and validate;
3. enable Snort last and validate `snort2c` immediately if the failure returns.

This avoids masking the actual source of the block with a broad whitelist.

## Useful pfSense commands

Current states for the public TrueNAS listener and an observed FastAPI Cloud source:

```sh
pfctl -ss | grep -E '52\.1\.10\.241|82\.66\.4\.247:7000'
```

Blocked packet log, when the block rule logs to `pflog0`:

```sh
tcpdump -n -e -ttt -i pflog0 'host 52.1.10.241 and dst port 7000'
```

Show HAProxy CSV header together with only the TrueNAS frontend/backend rows on one shell line:

```sh
echo "show stat" | socat stdio /tmp/haproxy.socket | grep -E '^(#|freenas,|freenas_ipvANY,)'
```

The header is important because HAProxy's runtime statistics are positional CSV fields. The key health indicators are the frontend `OPEN` state, backend/server `UP`, and a server health check such as `L7OK` with HTTP `200`.
