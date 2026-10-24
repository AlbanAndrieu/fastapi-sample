#!/usr/bin/env bash
# Read-only evidence from TrueNAS or an external workstation.
set -euo pipefail

runtime_url="${FASTAPI_RUNTIME_URL:-http://172.17.0.24:8091}"
mode=basic
vantage=auto
dns_only=0
while (($#)); do
  case "$1" in
    --strict) mode=strict ;;
    --detail) mode=report ;;
    --dns-only) dns_only=1 ;;
    --vantage)
      [[ $# -ge 2 ]] || { echo '❌ --vantage requires a value' >&2; exit 2; }
      vantage="$2"
      shift ;;
    --help|-h)
      printf 'Usage: %s [--strict|--detail|--dns-only] [--vantage auto|truenas|workstation]\n' "$0"
      exit 0 ;;
    *) printf '❌ Unknown option: %s\n' "$1" >&2; exit 2 ;;
  esac
  shift
done

case "$vantage" in
  auto)
    local_host="$(hostname -s 2>/dev/null || true)"
    if [[ "${local_host,,}" == "truenas" ]]; then
      vantage=truenas
    else
      vantage=workstation
    fi ;;
  truenas|workstation) ;;
  *) echo '❌ Invalid vantage' >&2; exit 2 ;;
esac

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
# DNS-only is independent from the cached FastAPI health-board helper.
# Keep it usable when that helper or the API runtime is unavailable.
if ((dns_only)); then
  exec python3 "$root/scripts/diagnose-homelab-dns.py" \
    --vantage "$vantage" --resolver-context --strict
fi

script="$root/scripts/diagnose-local-runtime-dependencies.py"
if [[ ! -f "$script" ]]; then
  echo '❌ FastAPI diagnostic script not found in this checkout.' >&2
  exit 2
fi

printf '📍 Observer=%s; target=TrueNAS (172.17.0.24)\n' "$vantage"
printf '\n🔎 FastAPI cached dependency evidence\n'
if [[ "$mode" == strict ]]; then
  python3 "$script" --url "$runtime_url" --wait-seconds 50 || exit $?
elif [[ "$mode" == report ]]; then
  python3 "$script" --url "$runtime_url" --wait-seconds 50 --report-only || exit $?
else
  python3 "$script" --url "$runtime_url" --wait-seconds 50 --basic || exit $?
fi

if [[ "$vantage" != truenas ]]; then
  echo '💻 Workstation: local Docker inventory (separate from TrueNAS).'
  if command -v docker >/dev/null 2>&1 && [[ -z "${DOCKER_HOST:-}${DOCKER_CONTEXT:-}" ]]; then
    for name in postgres redis; do
      if docker inspect "$name" >/dev/null 2>&1; then
        local_status="$(docker inspect --format '{{.State.Status}}' "$name" 2>/dev/null || true)"
        local_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' "$name" 2>/dev/null || true)"
        printf '💻 local %-10s state=%s health=%s (not TrueNAS evidence)\n' "$name" "$local_status" "$local_health"
      else
        printf '❔ local %-10s not found by exact name (not TrueNAS evidence)\n' "$name"
      fi
    done
  else
    echo 'ℹ️ Docker CLI not available or remote context configured; skipping local inventory.'
  fi
elif [[ -n "${DOCKER_HOST:-}" || -n "${DOCKER_CONTEXT:-}" ]]; then
  echo '⚠️ Explicit Docker host/context set: skipping ambiguous inventory.'
elif ! command -v docker >/dev/null 2>&1; then
  echo '⚠️ Docker CLI unavailable on TrueNAS.'
else
  printf '\n🐳 TrueNAS Docker inventory (metadata only)\n'
  if names="$(docker ps -a --format '{{.Names}}' 2>/dev/null)"; then
    for service in postgresql redis sentry gatus prometheus pyroscope; do
      case "$service" in
        postgresql) name=ix-postgres-postgres-1 ;;
        sentry) name=ix-sentry-sentry-web-1 ;;
        *) name="$service" ;;
      esac
      if ! grep -Fxq -- "$name" <<< "$names"; then
        printf '❔ %-12s %s not found\n' "$service" "$name"
        continue
      fi
      status="$(docker inspect --format '{{.State.Status}}' "$name" 2>/dev/null || true)"
      health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' "$name" 2>/dev/null || true)"
      printf '🐳 %-12s %-37s state=%s health=%s\n' "$service" "$name" "${status:-unknown}" "${health:-unknown}"
    done
  else
    echo '⚠️ Docker socket unavailable; no container evidence collected.'
  fi
fi

if command -v curl >/dev/null 2>&1; then
  printf '\n📡 TrueNAS network endpoints (read-only; from %s)\n' "$vantage"
  gatus_http=unknown
  prometheus_http=unknown
  pyroscope_http=unknown
  for item in 'gatus|http://172.17.0.24:8085/' 'prometheus|http://172.17.0.24:9090/-/ready' 'pyroscope|http://172.17.0.24:4040/ready'; do
    service="${item%%|*}"
    url="${item#*|}"
    curl_exit=0
    status="$(curl -sS -o /dev/null --connect-timeout 2 --max-time 5 -w '%{http_code}' "$url" 2>/dev/null)" || curl_exit=$?
    if [[ "$status" == 2* ]]; then
      symbol='✅'
      result='available'
    elif [[ "$status" == 000 ]]; then
      symbol='❌'
      result='unreachable'
      case "$curl_exit" in
        7) result='connection failed (curl 7; listener or route)' ;;
        28) result='timeout (curl 28; origin did not respond)' ;;
        6) result='DNS lookup failed (curl 6)' ;;
        *) result="transport error (curl $curl_exit)" ;;
      esac
    else
      symbol='⚠️'
      result='HTTP responded; readiness not confirmed'
    fi
    printf '%s %-12s HTTP=%s (%s)\n' "$symbol" "$service" "$status" "$result"
    case "$service" in
      gatus) gatus_http="$status" ;;
      prometheus) prometheus_http="$status" ;;
      pyroscope) pyroscope_http="$status" ;;
    esac
  done
fi
echo 'ℹ️ Cached board = transport observations; HTTP readiness below is independent evidence.'
if [[ "${gatus_http:-unknown}" == 200 ]]; then
  echo '✅ Gatus HTTP: available from this vantage; missing cached metric is a reconciliation gap.'
fi
if [[ "${pyroscope_http:-unknown}" == 200 ]]; then
  echo '✅ Pyroscope readiness: recovered at this vantage; profile ingestion remains unverified.'
elif [[ "${pyroscope_http:-unknown}" == 503 ]]; then
  echo '⚠️ Pyroscope readiness: HTTP 503 now; inspect with nabla-compose.'
fi
echo 'ℹ️ Basic reachability is not authenticated SQL/PING or Sentry/Gatus persistence.'
echo '🔧 Deep diagnostics live in nabla-compose:'
echo '   scripts/truenas/diagnose-fastapi-integrations.py'
echo '   scripts/truenas/diagnose-sentry.sh --check'
echo '   scripts/truenas/diagnose-gatus.sh'
echo '   scripts/truenas/diagnose-pyroscope.sh'
