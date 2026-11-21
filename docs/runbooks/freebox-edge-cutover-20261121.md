# Freebox observation after pfSense retirement (21 November 2026)

**CODED / NOT_DEPLOYED, no live Freebox probe performed from this environment.**
Netgate 1100 and HAProxy were removed on 18 November. Keep pfSense
probe implementations for history and future appliance reinstall, but do not
treat their failure as a current production outage.

## Runtime opt-in

TrueNAS Compose now sets `NETWORK_EDGE_PROVIDER=freebox` and
`FREEBOX_BASE_URL=http://192.168.1.254` (the upstream Freebox behind
the Netgear R7000 on `172.17.0.1`). Set **`NETWORK_EDGE_PROVIDER=freebox`**
independently in **FastAPI Cloud**. No Freebox private address should be
configured as a public Internet target.

- When freebox is selected, pfSense liveness/posture observers are skipped
  without I/O, the deprecated `/sickz` pfSense WAN/HAProxy row is not forced,
  and retired pfSense Unbound cannot make the aggregate critical health fail.
  Code for `NETWORK_EDGE_PROVIDER=pfsense` remains available.
- The LAN check performs **one GET** to
  `http://192.168.1.254/api_version`, bounded to three seconds, no
  redirects, no cookies, no Freebox session and no proxy environment.
  Success proves Freebox API discovery only; it does **not** prove WAN,
  fibre, upstream gateway, DHCP, NAT, DNS or IPv6 connectivity.
- FastAPI Cloud explicitly returns `skipped` / `unknown` for Freebox
  because it cannot prove private-LAN reachability. The public smoke requires
  this non-assertion, preventing false DOWN and false green.
- Do not configure `PFSENSE_POSTURE_API_KEY` or `PFSENSE_SECURITY_API_KEY`
  for the new edge. They can remain in Vaultwarden, but must not be used.

## Next LAN evidence and credentials

**Reuse the already-authorized `Nabla edge` Freebox OS App** from
`nabla-compose` (`app_id=fr.nabla.edge`), not a new Freebox App.
The original `scripts/pfsense/freebox-edge.py` uses its existing
`FREEBOX_APP_TOKEN` Vaultwarden item, Freebox-pinned HTTPS CA and Freebox
session challenge for bounded authenticated read-only checks of WAN mode/link,
IPv4/IPv6, LAN DHCP and DNS. The user confirmed that this App is authorized.

On a trusted LAN workstation with an unlocked Vaultwarden session, perform
a **read-only** acceptance:
```bash
# Repo: nabla-compose. Secret is consumed locally, never printed.
FREEBOX_APP_TOKEN="$(bw get password FREEBOX_APP_TOKEN)" \
  python3 scripts/pfsense/freebox-edge.py check --expect-mode router
```

Before considering FastAPI integration, export only *redacted* observations
from the existing trusted Compose collector to Prometheus/TrueNAS, then have
FastAPI consume those observations with provenance, TTL and unknown/stale
states. Do not duplicate the high-privilege Freebox App token in a public-facing
FastAPI service, GitHub Actions, FastAPI Cloud or a browser. The current
FastAPI LAN discovery uses no credentials and is not a substitute for the
existing `nabla-compose` authenticated check.

Validation after deployment:

1. On TrueNAS: confirm `curl -fsS --max-time 3 http://192.168.1.254/api_version`
   returns a JSON `api_version` (a redirect or response other than 200
   requires endpoint investigation, never disable verification globally).
2. Read authenticated `/healthz` and `/api/homelab/health` via the
   existing service smoke identity. Expect `checks.pfsense.skipped=true`,
   and on TrueNAS `checks.freebox.state=ok` only if the API responded.
3. On FastAPI Cloud: `checks.freebox.skipped=true` and
   `vantage_point=fastapi_cloud`; do not demand the private Freebox API
   from GitHub-hosted runners.
4. Check Gatus/Prometheus topology after the `nabla-compose` apply and
   mark legacy pfSense monitors disabled, not deleted.

Config and test contracts are in `nabla/api/freebox_health.py`,
`nabla/api/edge_provider.py`, `tests/unit/test_freebox_health.py`
and `.github/workflows/master-smoke.yml`.
