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
pfSense WAN / homelab public endpoint: 82.66.4.247
  |
  v
HAProxy :7000
  |
  | TLS re-encryption
  v
TrueNAS 172.17.0.24:7000
```

`82.66.4.247` is the homelab static public IPv4 assigned by Free and is named **pfSense WAN / homelab public endpoint** in the operations UI. The application exposes it as non-secret diagnostic metadata. The defaults may be overridden with `HOMELAB_WAN_IPV4` and `HOMELAB_WAN_PROVIDER` if the ISP or address changes.

## FastAPI Cloud source IPs

During the 2026-09-02 investigation, synchronized WAN captures observed requests from several cloud egress addresses, including `52.1.10.241`, `54.164.107.133`, and `34.200.20.162`. The latter was the effective source address during the controlled Snort block/recovery test.

Treat these addresses as **observed egress**, not as a permanent FastAPI Cloud allowlist contract. Do not assume that another deployment, replica, region, or platform change will keep the same address. In particular, do not broadly allowlist the surrounding AWS range solely to make the health probe work.

### Identify an observed source address

Use several independent signals rather than a geolocation label alone:

1. RDAP/WHOIS identifies the registered network owner and allocation.
2. BGP/ASN lookup identifies the network currently originating the prefix.
3. Reverse DNS can provide a useful hostname hint, but absence of PTR data is normal and a PTR is not proof of workload identity.
4. For a known cloud owner, compare the address with that provider's published IP-prefix data to identify a service/region when the provider publishes such metadata.
5. Correlate the address with a synchronized application request and pfSense state/capture before concluding that it is the current FastAPI Cloud egress.

Useful shell examples are:

```sh
whois 34.200.20.162
host 34.200.20.162
```

FastAPI Sample may expose its **currently observed outbound public IP** using a bounded, cached external echo request and then correlate that value with read-only pfSense table evidence. Such telemetry remains informational: it never rewrites firewall aliases, suppressions, pass lists, or rules, and it never assumes the observed address is a stable FastAPI Cloud contract.

A WAN capture for one refresh can be restricted to the observed source:

```sh
tcpdump -nnvi mvneta0.4090 'host 34.200.20.162 and tcp port 7000'
```

An accepted connection contains the TCP three-way handshake:

```text
34.200.20.162:<ephemeral> -> 82.66.4.247:7000  SYN
82.66.4.247:7000         -> 34.200.20.162:<ephemeral>  SYN,ACK
34.200.20.162:<ephemeral> -> 82.66.4.247:7000  ACK
```

- `SYN` requests a TCP connection.
- `SYN,ACK` proves that the destination accepted the TCP connection.
- `ACK` completes TCP establishment.
- TLS starts only after this handshake.
- `RST` is an explicit refusal/reset.
- repeated inbound `SYN` packets with no `SYN,ACK` or `RST` indicate a silent drop before TLS.

TLS certificate settings cannot fix a no-`SYN,ACK` condition because TLS has not started yet.

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

The public certificate observed on 2026-09-01 was `CN=*.albandrieu.com`, issued by Let's Encrypt `YR2`, matched `truenas.albandrieu.com`, and verified successfully. Keep `TRUENAS_API_VERIFY_SSL=true` for this public HAProxy endpoint. The diagnostic TLS context requires TLS 1.2 or newer.

## Ingress filtering telemetry

The FastAPI operations UI distinguishes **possible filtering layers** from proven block attribution. The sanitized pfSense observer reuses `/api/v2/status/services` to expose service-state evidence for:

- pfSense/PF firewall: normally shown as `in_path`;
- Snort: `running`, `stopped`, `unknown`, or `not_observed`;
- pfBlockerNG: `running`, `stopped`, `unknown`, or `not_observed` when a corresponding service is exposed;
- CrowdSec: `running`, `stopped`, `unknown`, or `not_observed`.

A `running` badge means only that the service was observed running. It does **not** prove that the layer blocked the FastAPI Cloud request.

For Snort, the observer additionally reads the pfSense diagnostics table `snort2c` and compares it with the runtime's bounded/cached public egress observation. Only an **exact IP match** is promoted to a proven block. When that evidence exists the TrueNAS platform displays, in red:

```text
Ingress blocked by Snort -> pfSense/PF
<observed FastAPI Cloud egress> -> 82.66.4.247:7000
Evidence: snort2c
```

If the pfSense API or the `snort2c` endpoint cannot be queried, the observer reports telemetry as unavailable rather than claiming Snort attribution. A failed external IP-echo lookup also remains non-fatal and never degrades `/healthz` or `/sickz` by itself.

The table lookup is read-only. The pfSense API key therefore needs GET access to `/api/v2/diagnostics/table`; no DELETE/table-mutation privilege is required by FastAPI Sample.

## Proven Snort / `snort2c` incident — 2026-09-02

Snort WAN was configured with:

```text
IPS Mode         = Legacy Mode
Block Offenders  = ON
Kill States      = ON
Which IP to Block = BOTH
```

The WAN Snort configuration also included TCP `7000` in the `http_inspect_server` port list. However, the public `82.66.4.247:7000` hop carries TLS to HAProxy. Snort therefore sees encrypted TLS bytes before HAProxy terminates TLS; it does not see the clear HTTP messages behind HAProxy.

The corresponding Snort preprocessor alerts were:

```text
[120:3]  (http_inspect) NO CONTENT-LENGTH OR TRANSFER-ENCODING IN HTTP RESPONSE
[120:18] (http_inspect) PROTOCOL-OTHER HTTP server response before client request
```

These alerts repeatedly occurred on flows from `82.66.4.247:7000` toward observed FastAPI Cloud egress addresses. Treating TLS `:7000` as clear-text HTTP is therefore consistent with false-positive HTTP Inspect classification.

During the failing test:

```sh
pfctl -t snort2c -T test 34.200.20.162
# 1/1 addresses match.
```

PF contained the generated bidirectional quick-drop rules:

```text
block drop log quick from <snort2c> to any
block drop log quick from any to <snort2c>
```

The WAN capture then showed repeated incoming `SYN` packets from `34.200.20.162` to `82.66.4.247:7000`, but no `SYN,ACK`. This proved that the flow was being discarded before HAProxy/TLS could respond.

The controlled recovery test was:

1. disable **Snort WAN only**;
2. remove only the observed test address from the table:

   ```sh
   pfctl -t snort2c -T delete 34.200.20.162
   ```

3. capture the same `34.200.20.162 -> 82.66.4.247:7000` flow again.

The next capture immediately showed `SYN -> SYN,ACK -> ACK`, followed by bidirectional application data and a normal TCP close. This A/B test establishes the causal chain:

```text
TLS :7000 misclassified by Snort HTTP Inspect
        -> HTTP Inspect alerts 120:3 / 120:18
        -> Block Offenders
        -> observed cloud egress inserted into snort2c
        -> PF block/drop quick
        -> Kill States / subsequent SYN silently dropped
        -> HAProxy and TrueNAS unreachable from that egress
```

### Correct Snort remediation

Do not solve this incident by permanently allowlisting `34.200.20.162`, `52.1.10.241`, or another single observed FastAPI Cloud address. The egress has already rotated.

Instead:

1. keep Snort WAN in Legacy Mode on this interface;
2. remove `7000` from the WAN **HTTP Inspect** server-port list;
3. keep HTTP Inspect enabled for genuine clear-text HTTP ports that need inspection;
4. optionally add `7000` to the Snort SSL/TLS preprocessor port list when that preprocessor is enabled/supported by the installed package;
5. do not hand-edit generated `snort.conf`, because pfSense regenerates it;
6. restart Snort WAN and retest the current egress against `snort2c`;
7. verify `SYN -> SYN,ACK -> ACK` and that `120:3`/`120:18` no longer recur for TLS `:7000`;
8. retain `Block Offenders` and `Kill States` only once that false-positive protocol classification has been corrected and validated.

Do not globally suppress all GID `120` events merely to hide this symptom. Do not use Inline Mode on the current `mvneta0.4090` interface unless its NIC/netmap support is independently proven.

## pfBlockerNG

First identify whether the block is an IP feed/alias block or DNSBL block. They are different mechanisms:

- an inbound FastAPI Cloud connection is filtered by its source IP, not by the hostname `fastapi-sample.fastapicloud.dev`;
- adding `fastapi-sample.fastapicloud.dev` to DNSBL whitelist does not allow an egress address through an IP block rule;
- if an IP feed is responsible, suppress or whitelist only a confirmed stable/trusted source contract rather than an entire cloud allocation.

Because FastAPI Cloud does not currently document a stable egress IP for this application, keep source-IP exceptions temporary and diagnostic unless a stable contract is established.

## CrowdSec

Check for an active decision before adding an exception:

```sh
cscli decisions list --ip <observed-egress-ip>
```

For a genuinely stable and trusted source, CrowdSec's preferred IP/CIDR mechanism is an AllowList. Do not create a permanent FastAPI Cloud AllowList until the platform provides a stable egress contract or repeated observations demonstrate an operationally acceptable range.

## Isolate the blocking engine

When diagnosing a recurrence, change one engine at a time. The 2026-09-02 incident demonstrated why restarting Snort, pfBlockerNG, and CrowdSec simultaneously makes attribution ambiguous.

A minimal Snort retest is:

1. start Snort WAN only after correcting the HTTP/TLS port classification;
2. determine the current FastAPI egress from a synchronized capture;
3. verify that address is not already in `snort2c`;
4. trigger one uncached TrueNAS health refresh;
5. inspect `snort2c`, Snort Alerts/SID, WAN `tcpdump`, and `pflog0` immediately.

## Useful pfSense commands

Test current Snort table membership:

```sh
pfctl -t snort2c -T test <observed-egress-ip>
```

Show the generated PF rules and counters:

```sh
pfctl -sr -vv | grep -B4 -A8 snort2c
```

Capture the public TrueNAS flow:

```sh
tcpdump -nnvi mvneta0.4090 'host <observed-egress-ip> and tcp port 7000'
```

Capture logged PF decisions:

```sh
tcpdump -nnevi pflog0 'host <observed-egress-ip> and tcp port 7000'
```

Show HAProxy CSV header together with only the TrueNAS frontend/backend rows on one shell line:

```sh
echo "show stat" | socat stdio /tmp/haproxy.socket | grep -E '^(#|freenas,|freenas_ipvANY,)'
```

A concise server-only summary is:

```sh
echo "show stat" | socat stdio /tmp/haproxy.socket | awk -F',' '$1=="freenas_ipvANY" && $2=="freenas" {print "proxy="$1,"server="$2,"scur="$5,"stot="$8,"status="$18,"check_status="$37,"check_code="$38,"check_duration_ms="$39}'
```

The 2026-09-02 observation returned `status=UP`, `check_status=L7OK`, `check_code=200`, and a 12 ms check duration against `172.17.0.24:7000`. This is strong evidence that the HAProxy backend-to-TrueNAS path was healthy at that instant. It does not prove that a WAN-side PF/Snort/pfBlocker/CrowdSec policy will accept every future source connection.
