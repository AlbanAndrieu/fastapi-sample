# pfSense WebGUI/API 502 recovery

Use this runbook when pfSense nginx is reachable but WebGUI or the lightweight
REST endpoint returns HTTP 502. The dated 2026-09 recurrences and their evidence
are recorded in [incidents.md](incidents.md).

## Interpretation

A native nginx 502 means the network/HTTP listener responded but the
webConfigurator/PHP backend failed. Authentication may not have been evaluated.

```text
pfSense
  network transport        reachable
  API/WebGUI control plane application error (HTTP 502)
  authentication           unknown until evaluated
  Prometheus/exporter      independent evidence
```

Do not classify this as a TCP failure or invalid API key without separate proof.

## Preferred helper

Read-only collection:

```bash
scripts/pfsense/diagnose-recover.sh --check
```

Reviewed recovery:

```bash
scripts/pfsense/diagnose-recover.sh --apply
```

The helper keeps `PFSENSE_POSTURE_API_KEY` on the workstation and captures a
bounded report containing:

- nginx/PHP-FPM/webConfigurator listeners, processes and logs;
- filesystem, swap, RSS and OOM/reclaim evidence;
- Unbound process/port/status and memory evidence;
- Snort/pfBlockerNG processes and relevant PF tables;
- exact block attribution for configured probe sources;
- PF rules/states involving management port `10443`;
- workstation WebUI and authenticated REST probes.

Only when a supplied host IP is an **exact** runtime table entry may the operator
opt into removal:

```bash
scripts/pfsense/diagnose-recover.sh --apply --unblock-sources
```

This deletes only exact supplied IP entries. It never flushes tables, removes
CIDRs/aliases or edits persistent firewall/Snort/pfBlockerNG policy.

Useful overrides:

```bash
scripts/pfsense/diagnose-recover.sh \
  --target root@172.17.0.1 \
  --probe-sources "172.17.0.24 172.17.0.57" \
  --api-url https://home.albandrieu.com:10443
```

## Preserve evidence before recovery

From pfSense shell:

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

find /var/log -maxdepth 2 -type f | \
  egrep -i 'nginx|php|fpm|webgui|webconfig' | sort
```

Capture this before restarts so socket/process/OOM evidence is not lost.

## Recover WebGUI/PHP-FPM without reboot

Prefer pfSense console options **11) Restart GUI** and **16) Restart PHP-FPM**,
or the supported shell helpers:

```sh
/etc/rc.php-fpm_restart
/etc/rc.restart_webgui

sockstat | grep nginx
pgrep -laf 'nginx|php-fpm'
```

Validate from the workstation:

```bash
curl -ksS -o /dev/null \
  -w 'ui http=%{http_code} peer=%{remote_ip} time=%{time_total}\n' \
  https://home.albandrieu.com:10443/

curl -sS -o /dev/null \
  -w 'api http=%{http_code} peer=%{remote_ip} tls=%{ssl_verify_result} time=%{time_total}\n' \
  -H "X-API-Key: ${PFSENSE_POSTURE_API_KEY}" \
  -H 'Accept: application/json' \
  https://home.albandrieu.com:10443/api/v2/system/version
```

Expected result: WebGUI 200/30x and authenticated version endpoint 2xx JSON.
Review `/crash_reporter.php` for sensitive configuration before sharing it.

## Treat Unbound separately

A WebGUI/PHP-FPM 502 does not prove an Unbound failure.

```sh
pgrep -laf unbound
sockstat | grep ':53'
unbound-control -c /var/unbound/unbound.conf status
```

If only Unbound is unhealthy, recover the resolver separately; a lighter reload
is:

```sh
unbound-control -c /var/unbound/unbound.conf reload
```

Do not reboot the firewall merely because one management/resolver service is
unhealthy.

## Probe safety

- cache and single-flight FastAPI pfSense probes;
- use one lightweight `/api/v2/system/version` attempt per failure window;
- never use expensive deep status as synchronous liveness;
- do not immediately retry 5xx responses;
- use `pfsense_exporter` for periodic runtime telemetry;
- keep Uptime Kuma/Gatus simple and low frequency;
- avoid synchronized polling intervals across monitors;
- during failure, prefer stale/unknown evidence over increased probe pressure.

## Acceptance

Close the pfSense runtime issue only when:

1. WebGUI/PHP-FPM recover without firewall reboot;
2. authenticated lightweight REST returns 2xx from the TrueNAS/LAN observer;
3. Unbound state is independently known;
4. exporter telemetry remains independent from REST control-plane evidence;
5. monitor frequencies are inventoried and do not create synchronized pressure;
6. recurrence capture preserves process/socket/log/OOM evidence before restart.
