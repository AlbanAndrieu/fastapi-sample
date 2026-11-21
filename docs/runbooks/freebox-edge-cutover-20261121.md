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

The existing `nabla-compose/scripts/pfsense/freebox-edge.py check` supports
more detailed Freebox OS inspection. A read-only inventory of WAN mode/link,
IPv4/IPv6, connection uptime, LAN DHCP and DNS can be added after the
**Freebox OS App authorization** has been approved locally. This requires
a **dedicated Freebox app_token**, acquired through Freebox OS and stored in
Vaultwarden, not the administrator password. Do not inject the token into
GitHub Actions, a public FastAPI Cloud process, or a browser. The current
Freebox discovery probe deliberately uses no credential.

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
