# FastAPI Cloud: Owner diagnostics denied from the home network

Incident, 21 October 2026. The home public IPv4 confirmed by the operator is `82.66.4.247`.

## Deployment evidence

GitHub Actions [run 39634265656](https://github.com/AlbanAndrieu/fastapi-sample/actions/runs/39634265656) failed at **Validate production candidate** with five pytest failures; **Deploy production** and **Verify deployed production externally** were skipped. Previous deployment run 39562478704 also failed. The UI string `Access denied (HTTP 403)` dates from the older client; current GitHub master contains more specific 403 handling, but the live deployment SHA cannot be verified from the agent environment.

## Operator checks (never share the key)

From the HOME network, first `curl -4 -s https://api.ipify.org`. Then request a session and print only the HTTP code and response body, never the key or `Set-Cookie`:

```bash
read -rsp 'Diagnostics key: ' DIAGNOSTICS_ACCESS_KEY; printf '\n'
curl -sS --max-time 15 -X POST \
  -H 'Origin: https://fastapi-sample.fastapicloud.dev' \
  -H 'Sec-Fetch-Site: same-origin' \
  -H 'Accept: application/json' \
  -H "X-Diagnostics-Key: ${DIAGNOSTICS_ACCESS_KEY}" \
  -w '\nHTTP %{http_code}\n' \
  https://fastapi-sample.fastapicloud.dev/api/ui/session
unset DIAGNOSTICS_ACCESS_KEY
```

* HTTP 403 with `source_unverified`: the server did not establish an allowlisted source IP. This check occurs **before validating the key**.
* HTTP 403 with `origin_unverified`: HTTPS Origin, Host or Sec-Fetch-Site did not pass same-origin validation. This check also happens **before validating the key**.
* HTTP 503 `unconfigured`: FastAPI Cloud does not have the operator secret configured.
* HTTP 401: origin and source gates passed; supplied key is invalid.
* HTTP 200: a short-lived Secure HttpOnly session was created; verify `GET /api/ui/session` and then `GET /api/health-board`.

The browser may show an older UI message if the cloud deploy is blocked; examine the JSON response, not just the display string. A direct `curl` with explicit Origin checks the POST route but does **not** reproduce a real browser's proxy and security headers exactly.

## Secure proxy remediation

`HOMELAB_TRUSTED_CIDRS=82.66.4.247/32` names the **client**. It does not configure the **trusted proxy**. `nabla/homelab_trusted_ip.py` rejects untrusted `X-Forwarded-For` and multi-hop or conflicting forwarded fields. Determine in private operator telemetry what `scope.client` reports, whether forwarding headers are overwritten by the ingress, and whether Uvicorn already normalizes the client. Do not log raw authorization headers or expose the actual proxy chain in a browser-facing response.

Configure `HOMELAB_TRUSTED_PROXY_CIDRS` only with verified immediate ASGI proxy peers and test that untrusted headers cannot spoof the home IP. Never set this variable to `0.0.0.0/0`, never trust `--forwarded-allow-ips='*'` by default, and never add Vercel server egress addresses to the homeowner allowlist.

Acceptance: legitimate home login succeeds, mobile/off-home and spoofed-header logins remain denied, `401` for incorrect key, and deployment smoke verifies exact active SHA. Do not treat the GitHub merge as deployment confirmation.
