#!/usr/bin/env bash
set -euo pipefail

MODE="check"
SSH_TARGET="${PFSENSE_SSH_TARGET:-root@172.17.0.1}"
API_URL="${PFSENSE_API_URL:-https://home.albandrieu.com:10443}"
LAN_API_URL="${PFSENSE_LAN_API_URL:-https://172.17.0.1:10443}"
PROBE_SOURCES="${PFSENSE_PROBE_SOURCES:-172.17.0.24 172.17.0.57}"
UNBLOCK_SOURCES=false
REPORT="${PFSENSE_RECOVERY_REPORT:-/tmp/pfsense-recovery-$(date +%Y%m%d-%H%M%S).log}"

usage() {
    cat <<'USAGE'
Usage: scripts/pfsense/diagnose-recover.sh [options]

Run this helper from the workstation. It SSHes to pfSense, captures bounded
nginx/PHP-FPM/webConfigurator, Unbound, Snort/pfBlockerNG and memory evidence,
and optionally performs narrowly-scoped recovery.

Options:
  --check                   Read-only diagnosis (default).
  --apply                   Restart PHP-FPM + webConfigurator/nginx and restart
                            Unbound only when its status was not proven healthy.
  --unblock-sources         With --apply only: delete exact source host entries
                            from dynamic snort2c/pfBlockerNG PF tables when a
                            BLOCK_MATCH was actually proven. Never flushes tables.
  --target USER@HOST        SSH target (default: root@172.17.0.1).
  --api-url URL             Workstation/public HTTPS URL.
  --lan-api-url URL         Direct LAN HTTPS URL used as a second vantage point.
  --probe-sources "IP ..."  Exact source IPs to attribute/unblock.
  --report PATH             Local report path.
  -h, --help                Show this help.

Environment:
  PFSENSE_POSTURE_API_KEY   Optional. Used only by workstation-side REST probes;
                            it is never sent through SSH and never printed.

Recommended sequence after a pfSense reboot:
  1. --check
  2. review the report
  3. --apply only if webConfigurator/PHP-FPM or Unbound needs recovery
  4. --apply --unblock-sources only if BLOCK_MATCH proves an exact host block
USAGE
}

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

while (($# > 0)); do
    case "$1" in
        --check)
            MODE="check"
            ;;
        --apply)
            MODE="apply"
            ;;
        --unblock-sources)
            UNBLOCK_SOURCES=true
            ;;
        --target)
            shift
            (($# > 0)) || fail "--target requires USER@HOST"
            SSH_TARGET="$1"
            ;;
        --api-url)
            shift
            (($# > 0)) || fail "--api-url requires URL"
            API_URL="$1"
            ;;
        --lan-api-url)
            shift
            (($# > 0)) || fail "--lan-api-url requires URL"
            LAN_API_URL="$1"
            ;;
        --probe-sources)
            shift
            (($# > 0)) || fail "--probe-sources requires a space-separated IP list"
            PROBE_SOURCES="$1"
            ;;
        --report)
            shift
            (($# > 0)) || fail "--report requires PATH"
            REPORT="$1"
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            fail "unknown option: $1"
            ;;
    esac
    shift
done

[[ "${API_URL}" == https://* ]] || fail "--api-url must use https://"
[[ "${LAN_API_URL}" == https://* ]] || fail "--lan-api-url must use https://"
if [[ "${UNBLOCK_SOURCES}" == true && "${MODE}" != "apply" ]]; then
    fail "--unblock-sources requires --apply"
fi

for command in ssh curl tee grep awk date mktemp; do
    command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

for source in ${PROBE_SOURCES}; do
    [[ "${source}" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || fail "invalid IPv4 probe source: ${source}"
done

mkdir -p "$(dirname "${REPORT}")"
printf 'pfSense recovery mode=%s target=%s api=%s lan_api=%s sources=%s\n' \
    "${MODE}" "${SSH_TARGET}" "${API_URL}" "${LAN_API_URL}" "${PROBE_SOURCES}"
printf 'Local report: %s\n' "${REPORT}"

SSH_OPTS=(
    -o BatchMode=yes
    -o ConnectTimeout=8
    -o ServerAliveInterval=5
    -o ServerAliveCountMax=2
)

# pfSense defaults to csh/tcsh for interactive shells, so always invoke /bin/sh
# explicitly for the remote payload.
ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" /bin/sh -s -- \
    "${MODE}" "${UNBLOCK_SOURCES}" "${PROBE_SOURCES}" <<'REMOTE' | tee "${REPORT}"
set -u
MODE="$1"
UNBLOCK_SOURCES="$2"
shift 2
PROBE_SOURCES="$*"

section() { printf '\n==> %s\n' "$1"; }
run_optional() { "$@" 2>&1 || true; }

section "Snapshot before mutation"
date
uptime
hostname
run_optional sockstat -4 -6 -l
ps axo pid,rss,vsz,pcpu,pmem,command 2>/dev/null | \
    egrep 'PID|nginx|php-fpm|unbound|snort|pfblocker|pfb_' || true
printf '\nTop RSS processes:\n'
ps axo pid,rss,vsz,pcpu,pmem,command 2>/dev/null | sort -nr -k2 | head -25 || true
run_optional df -h
run_optional df -i
run_optional swapinfo -h
printf '\nKernel memory/reclaim evidence:\n'
dmesg 2>/dev/null | \
    egrep -i 'killed|failed to reclaim|waited too long|out of swap|out of memory|oom' | \
    tail -80 || true

section "nginx / PHP-FPM / webConfigurator"
NGINX_RUNNING=false
PHP_FPM_RUNNING=false
pgrep -f '[n]ginx' >/dev/null 2>&1 && NGINX_RUNNING=true
pgrep -f '[p]hp-fpm' >/dev/null 2>&1 && PHP_FPM_RUNNING=true
printf 'nginx_process=%s\n' "${NGINX_RUNNING}"
printf 'php_fpm_process=%s\n' "${PHP_FPM_RUNNING}"
if command -v nginx >/dev/null 2>&1; then
    run_optional nginx -t
fi
if command -v php-fpm >/dev/null 2>&1; then
    run_optional php-fpm -t
elif [ -x /usr/local/sbin/php-fpm ]; then
    run_optional /usr/local/sbin/php-fpm -t
fi
sockstat 2>/dev/null | egrep 'nginx|php-fpm|:443|:10443' || true
pgrep -laf 'nginx|php-fpm' 2>/dev/null || true
printf '\nFastCGI/upstream configuration hints:\n'
grep -R -nE 'fastcgi_pass|upstream|php-fpm|fastcgi' \
    /var/etc/nginx* /usr/local/etc/nginx 2>/dev/null | head -120 || true
printf '\nRelevant log files:\n'
WEB_LOGS="$(find /var/log -maxdepth 2 -type f 2>/dev/null | \
    egrep -i 'nginx|php|fpm|webgui|webconfig' | sort | head -20 || true)"
printf '%s\n' "${WEB_LOGS:-<none>}"
for logfile in ${WEB_LOGS}; do
    printf '\n--- %s (tail) ---\n' "${logfile}"
    tail -n 80 "${logfile}" 2>/dev/null || true
done
printf '\nSystem log web/backend evidence:\n'
tail -n 450 /var/log/system.log 2>/dev/null | \
    egrep -i 'nginx|php|fpm|webconfig|fatal|segfault|signal|killed|memory|out of memory|crash|502|upstream|error' | \
    tail -220 || true
printf '\nCrash artifacts metadata (content intentionally not dumped):\n'
find /var/crash /var/db -maxdepth 2 -type f 2>/dev/null | \
    egrep -i 'crash|core|php|nginx' | head -80 || true

section "Unbound"
UNBOUND_HEALTHY=false
UNBOUND_PROCESS=false
UNBOUND_PORT=false
pgrep -f '[u]nbound' >/dev/null 2>&1 && UNBOUND_PROCESS=true
sockstat 2>/dev/null | grep ':53' | head -30 || true
sockstat 2>/dev/null | grep ':53' >/dev/null 2>&1 && UNBOUND_PORT=true
printf 'unbound_process=%s unbound_port53=%s\n' "${UNBOUND_PROCESS}" "${UNBOUND_PORT}"
if command -v unbound-control >/dev/null 2>&1 && [ -f /var/unbound/unbound.conf ]; then
    if unbound-control -c /var/unbound/unbound.conf status 2>&1; then
        UNBOUND_HEALTHY=true
    fi
    unbound-control -c /var/unbound/unbound.conf stats_noreset 2>/dev/null | \
        egrep '^mem\.' | head -80 || true
fi
printf 'unbound_control_healthy=%s\n' "${UNBOUND_HEALTHY}"
grep -nEi '<dnsbl_mode>|<pfb_tld>|<regdhcp>|<regdhcpstatic>' \
    /conf/config.xml 2>/dev/null | head -80 || true
grep -nE 'module-config|python-script|msg-cache-size|rrset-cache-size' \
    /var/unbound/unbound.conf 2>/dev/null | head -80 || true

section "Snort / pfBlockerNG / PF attribution"
pgrep -laf 'snort|pfblocker|pfb_' 2>/dev/null || true
TABLES="$(pfctl -s Tables 2>/dev/null | egrep '^(snort2c|pfB_|pfb_)' || true)"
printf 'candidate_tables:\n%s\n' "${TABLES:-<none>}"
printf '\nRules/states involving management port 10443:\n'
pfctl -sr 2>/dev/null | grep '10443' | head -80 || true
pfctl -ss 2>/dev/null | grep '10443' | head -80 || true

BLOCK_MATCH_COUNT=0
for source in ${PROBE_SOURCES}; do
    printf '\nsource=%s\n' "${source}"
    for table in ${TABLES}; do
        if pfctl -t "${table}" -T show 2>/dev/null | \
            awk -v ip="${source}" '$1 == ip {found=1} END {exit !found}'; then
            BLOCK_MATCH_COUNT=$((BLOCK_MATCH_COUNT + 1))
            echo "BLOCK_MATCH table=${table} source=${source} exact=yes"
            if [ "${MODE}" = apply ] && [ "${UNBLOCK_SOURCES}" = true ]; then
                case "${table}" in
                    snort2c | pfB_* | pfb_*)
                        echo "UNBLOCK_ACTION table=${table} source=${source}"
                        pfctl -t "${table}" -T delete "${source}" 2>&1 || true
                        ;;
                esac
            fi
        fi
    done
    pfctl -ss 2>/dev/null | grep "${source}" | head -30 || true
done
printf '\nblock_match_count=%s\n' "${BLOCK_MATCH_COUNT}"
if [ "${BLOCK_MATCH_COUNT}" -gt 0 ] && [ "${MODE}" = check ]; then
    echo 'ACTION_HINT: exact dynamic block proven; review evidence, then use --apply --unblock-sources if appropriate.'
fi

if [ "${MODE}" = apply ]; then
    section "Targeted recovery actions"
    echo 'Restarting PHP-FPM using pfSense rc helper...'
    /etc/rc.php-fpm_restart 2>&1 || true
    sleep 2
    echo 'Restarting webConfigurator/nginx using pfSense rc helper...'
    /etc/rc.restart_webgui 2>&1 || true
    sleep 3

    if [ "${UNBOUND_HEALTHY}" != true ]; then
        echo 'Unbound was not proven healthy; restarting resolver only.'
        if [ -x /usr/local/sbin/pfSsh.php ]; then
            /usr/local/sbin/pfSsh.php playback svc restart unbound 2>&1 || true
        elif [ -x /etc/rc.d/unbound ]; then
            /etc/rc.d/unbound restart 2>&1 || true
        else
            echo 'WARN: no supported Unbound restart helper found'
        fi
        sleep 3
    else
        echo 'Unbound already healthy; no resolver restart.'
    fi
else
    section "No mutation"
    echo 'check mode: no service restart and no PF table mutation performed'
fi

section "Post-action appliance state"
pgrep -laf 'nginx|php-fpm|unbound|snort|pfblocker|pfb_' 2>/dev/null || true
sockstat 2>/dev/null | egrep 'nginx|php-fpm|:53|:443|:10443' | head -120 || true
if command -v unbound-control >/dev/null 2>&1 && [ -f /var/unbound/unbound.conf ]; then
    unbound-control -c /var/unbound/unbound.conf status 2>&1 || true
fi

if [ "${MODE}" = apply ] && [ "${UNBLOCK_SOURCES}" = true ]; then
    printf '\nRechecking exact Snort/pfBlockerNG block entries after deletion:\n'
    for source in ${PROBE_SOURCES}; do
        for table in ${TABLES}; do
            if pfctl -t "${table}" -T show 2>/dev/null | \
                awk -v ip="${source}" '$1 == ip {found=1} END {exit !found}'; then
                echo "BLOCK_REAPPEARED table=${table} source=${source} exact=yes"
            fi
        done
    done
fi

dmesg 2>/dev/null | \
    egrep -i 'killed|failed to reclaim|waited too long|out of swap|out of memory|oom' | \
    tail -80 || true
REMOTE

probe_url() {
    local label="$1"
    local url="$2"
    local insecure="$3"
    local curl_tls=()
    if [[ "${insecure}" == true ]]; then
        curl_tls=(-k)
    fi
    curl "${curl_tls[@]}" -sS -o /dev/null --connect-timeout 5 --max-time 15 \
        -w "${label} http=%{http_code} peer=%{remote_ip} tls=%{ssl_verify_result} time=%{time_total}\\n" \
        "${url%/}/" || true
}

probe_api() {
    local label="$1"
    local url="$2"
    local insecure="$3"
    local tmp_body http_code body_type
    local curl_tls=()
    if [[ "${insecure}" == true ]]; then
        curl_tls=(-k)
    fi
    tmp_body="$(mktemp)"
    http_code="$(curl "${curl_tls[@]}" -sS -o "${tmp_body}" \
        --connect-timeout 5 --max-time 15 -w '%{http_code}' \
        -H "X-API-Key: ${PFSENSE_POSTURE_API_KEY}" \
        -H 'Accept: application/json' \
        "${url%/}/api/v2/system/version" || true)"
    if grep -q '^[[:space:]]*[\[{]' "${tmp_body}"; then
        body_type=json
    else
        body_type=non-json
    fi
    printf '%s authenticated http=%s body_type=%s\n' \
        "${label}" "${http_code:-000}" "${body_type}"
    rm -f "${tmp_body}"
}

printf '\n==> Workstation-side verification\n' | tee -a "${REPORT}"
{
    probe_url 'ui_public' "${API_URL}" false
    # Direct-IP LAN verification intentionally disables certificate validation;
    # its purpose is transport/application comparison, not hostname trust.
    probe_url 'ui_lan' "${LAN_API_URL}" true

    if [[ -n "${PFSENSE_POSTURE_API_KEY:-}" ]]; then
        probe_api 'api_public' "${API_URL}" false
        probe_api 'api_lan' "${LAN_API_URL}" true
    else
        printf '? PFSENSE_POSTURE_API_KEY unset: authentication not evaluated\n'
    fi
} | tee -a "${REPORT}"

printf '\nReport saved to %s\n' "${REPORT}"
printf 'Next step: review BLOCK_MATCH/BLOCK_REAPPEARED, nginx/PHP-FPM and Unbound evidence before any further package or firewall action.\n'
