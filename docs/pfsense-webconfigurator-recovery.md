# pfSense webConfigurator 502 recovery and probe safety

## Incident signature — 2026-09-10

The pfSense management path is reachable from both the workstation and the
TrueNAS-hosted FastAPI runtime, but the pfSense webConfigurator currently
returns an application-side `502` for the lightweight REST liveness endpoint:

```text
GET https://home.albandrieu.com:10443/api/v2/system/version
HTTP/2 502
server: nginx
content-type: text/html
```

The response body is the native pfSense `50x Error` page and explicitly points
to `/crash_reporter.php`. This means DNS, TCP, TLS and the HTTP listener are not
the current blocker: nginx accepted the request, but the pfSense web/PHP backend
failed while processing it.

Observed vantage points:

```text
workstation:
  home.albandrieu.com -> 82.66.4.247
  TLS verification   -> success
  HTTP               -> 502

FastAPI on TrueNAS:
  home.albandrieu.com -> 172.17.0.1
  HTTP               -> 502
```

The same `502` is returned without an API key from the TrueNAS container, so the
current failure happens before API-key authentication can be evaluated. Keep
authentication state `unknown`, not `failed`.

## Desired platform representation

Until the API backend is recovered, represent pfSense as multiple independent
signals rather than collapsing the appliance to DOWN:

```text
pfSense platform
  ⚠️ API control-plane       application error (HTTP 502)
  ✅ Prometheus telemetry    exporter up
  ✅ network transport       reachable
  ? API authentication      not evaluated
```

A HTTP `502` from pfSense nginx is transport evidence plus an application
failure. It is not a connect failure and must not be treated as proof that the
API credential is invalid.

## Immediate recovery — preserve evidence first

Prefer console or SSH access to pfSense itself. Before restarting anything,
capture a bounded diagnostic snapshot from console menu option **8) Shell**:

```sh
date
uptime
sockstat | egrep 'nginx|php-fpm|unbound'
pgrep -laf 'nginx|php-fpm|unbound'
df -h
df -i
swapinfo -h

tail -n 250 /var/log/system.log | \
  egrep -i 'nginx|php|fpm|unbound|fatal|segfault|signal|killed|memory|out of memory|crash|error'
```

Recent pfSense releases use ordinary text logs under `/var/log`; inspect the
system log before restarting services so the original failure evidence is not
lost in later noise.

Also inventory any web/PHP-specific logs that exist on the appliance without
assuming a release-specific filename:

```sh
find /var/log -maxdepth 2 -type f | \
  egrep -i 'nginx|php|fpm|webgui|webconfig' | sort
```

Then tail only the files that exist and are relevant.

### Recover webConfigurator without rebooting pfSense

Netgate documents console option **11) Restart GUI** to restart nginx and option
**16) Restart PHP-FPM** when nginx is alive but PHP cannot execute requests.
Use them together for this failure signature.

From the shell, the equivalent supported rc scripts are:

```sh
/etc/rc.restart_webgui
/etc/rc.php-fpm_restart
```

After both complete, verify listeners/processes:

```sh
sockstat | grep nginx
pgrep -laf 'nginx|php-fpm'
```

Then validate externally from the workstation:

```sh
curl -ksS -o /dev/null \
  -w 'ui http=%{http_code} peer=%{remote_ip} time=%{time_total}\n' \
  https://home.albandrieu.com:10443/

curl -sS -o /dev/null \
  -w 'api http=%{http_code} peer=%{remote_ip} tls=%{ssl_verify_result} time=%{time_total}\n' \
  -H "X-API-Key: ${PFSENSE_POSTURE_API_KEY}" \
  -H 'Accept: application/json' \
  https://home.albandrieu.com:10443/api/v2/system/version
```

Expected recovery:

```text
webConfigurator root -> 200/30x
/api/v2/system/version with posture key -> 2xx JSON
```

If the GUI is restored, inspect `/crash_reporter.php` before clearing anything.
Do not publish the crash report verbatim without reviewing it for private
configuration or network data.

## Unbound is a separate failure domain

A webConfigurator/PHP-FPM `502` does not by itself prove that Unbound caused the
failure. Check DNS Resolver state independently:

```sh
pgrep -laf unbound
sockstat | grep ':53'
unbound-control -c /var/unbound/unbound.conf status
```

If Unbound alone is unhealthy, restart only the resolver or use the pfSense
Status > Services control. Netgate documents a resolver restart to clear the
cache, and also supports a lighter reload:

```sh
unbound-control -c /var/unbound/unbound.conf reload
```

Do not repeatedly restart the entire firewall merely because the resolver or
webConfigurator is unhealthy.

## Protect pfSense from monitoring pressure

The management API and webConfigurator are appliances, not high-throughput
monitoring endpoints. FastAPI, Prometheus, Uptime Kuma and other monitoring must
not create synchronized or high-frequency probes against them.

Required policy:

- keep FastAPI pfSense probes cached, bounded and single-flight;
- one lightweight `/api/v2/system/version` origin attempt per failure window;
- do not use `/api/v2/status/system` as a synchronous liveness probe;
- do not immediately retry a 5xx response;
- use Prometheus `pfsense_exporter` for periodic runtime telemetry instead of
  repeatedly querying expensive REST status endpoints;
- keep Uptime Kuma on a simple low-frequency GUI/TCP/HTTP availability probe;
- avoid placing FastAPI, Prometheus and Uptime Kuma on identical polling
  intervals that can synchronize into bursts;
- while pfSense returns 5xx, let caches/circuit breakers suppress origin calls
  and expose stale/unknown evidence rather than increasing probe pressure.

Before attributing a future crash to monitoring, correlate the exact crash
window with access logs/process resource evidence and per-client request counts.
A temporal overlap is not sufficient by itself.

## Preferred privilege architecture

The durable architecture is LAN-side observation with sanitized publication:

```text
pfSense
    | read-only REST API over LAN
    v
FastAPI TrueNAS observer
    | normalized/sanitized state
    +--> FastAPI health board / private diagnostics
    +--> optional outbound authenticated projection for FastAPI Cloud

pfSense --> pfsense_exporter --> Prometheus --> runtime telemetry
```

FastAPI Cloud must not require broad direct Internet access to the pfSense
management API. Direct WAN `:10443` remains diagnostic only while there is no
stable application-controlled egress identity.

The first priority is therefore to make **FastAPI TrueNAS -> pfSense LAN** safe
and reliable. Only after that path is accepted should FastAPI Cloud consume a
sanitized out-of-band projection rather than raw privileged pfSense responses.

## Acceptance criteria

Do not close the pfSense runtime work until all of the following are proven:

1. webConfigurator and PHP-FPM recover without a firewall reboot;
2. the bounded authenticated `/api/v2/system/version` call returns `2xx` from
    the FastAPI TrueNAS runtime path;
3. Unbound state is independently known and no DNS dependency loop through
    TrueNAS/Pi-hole can make LAN clients lose resolution when an app host fails;
4. Prometheus `pfsense_exporter` remains operational and is treated as telemetry,
    not a replacement for authoritative REST control-plane state;
5. FastAPI/Uptime Kuma/Prometheus polling frequencies are inventoried and proven
    not to create synchronized pressure against pfSense;
6. a recurrence captures nginx/PHP-FPM/Unbound/process/log evidence before
    service restarts;
7. any remaining risk or deferred hardening remains recorded in
    `docs/engineering-roadmap.md`.
