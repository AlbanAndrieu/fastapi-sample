# Garage public-ingress audit

Use this runbook when a Garage hostname is marked `external=false` but answers from the public Internet. Do not paste complete Cloudflare Access `Location` headers into issues or chat: query parameters can contain short-lived signed metadata.

## 1. Confirm the catalog (Cloud API)

Set `API` explicitly; an unset or empty value causes curl's `URL rejected: No host part`.

```bash
export API="${API:-https://fastapi-sample.fastapicloud.dev}"
: "${DIAGNOSTICS_ACCESS_KEY:?Export DIAGNOSTICS_ACCESS_KEY first}"

curl -fsS --connect-timeout 5 --max-time 20 \
  -H "X-Diagnostics-Key: $DIAGNOSTICS_ACCESS_KEY" \
  "$API/api/homelab-services" |
jq '[.services[] | select((.id // "") | startswith("garage")) |
    {id, name, external, internalPort, tunnelUrl}]'
```

A catalogue value of `external=false` describes desired exposure; it does not prove that public DNS, Cloudflare Tunnel, HAProxy or NAT agrees.

## 2. Inspect public edge response without leaking Access tokens

```bash
for host in garage-admin.albandrieu.com s3.int.albandrieu.com garage.albandrieu.com; do
  printf '\n== %s ==\n' "$host"
  curl -sS -D - -o /dev/null --connect-timeout 5 --max-time 10 \
    "https://$host/" |
  awk 'BEGIN { IGNORECASE=1 }
    /^HTTP\// || /^server:/ || /^cf-ray:/ { print }
    /^location:/ { sub(/\?.*/, "?<redacted>", $0); print }'
done
```

Interpretation:
- A Cloudflare `302` to `*.cloudflareaccess.com/.../login/...` confirms a public edge/Access route is responding. It does not prove the origin is anonymously reachable or identify the origin port.
- `server: cloudflare` alone does not establish that the origin is Cloudflare Tunnel; confirm the configured route in Cloudflare Zero Trust.
- A response from the LAN to a hostname does not establish external reachability; use a device/network outside the LAN for outside-in validation.

## 3. Reconcile declared and actual routing

For each hostname, compare:
1. Catalog intent (`external`, `internalHost`, `internalPort`, `tunnelUrl`).
2. Public DNS (`dig +short CNAME <hostname>` and `dig +short A <hostname>`).
3. Cloudflare Zero Trust → Networks → Tunnels → the active tunnel → Public Hostnames / published application routes, including the configured origin URL and port.
4. pfSense HAProxy frontend/backend and NAT rules, then Traefik routers/services and their target ports.
5. Outside-in response and LAN response, recorded separately.

For `garage-admin.albandrieu.com`, a public Cloudflare Access login redirect was observed on 2026-10-15. This is a **publicly reachable Access gate**, not proof of anonymous origin access. Since Garage Admin API is intended to be private, remove its public hostname/tunnel ingress and any associated public DNS publication after verifying which configuration source owns them. Do not merely rely on Access as a substitute for the private-only policy.

Expected service ports on TrueNAS:
- Garage S3 API: `:3900`, private only.
- Garage Admin API: `:3903`, private only.
- Garage Web UI: `:3909`, temporarily public by explicit user decision, behind appropriate access control.

## 4. Record evidence precisely

Report each layer as `matched`, `drift`, or `unknown`. A missing credential/API response is `unknown`, not proof that no route exists. Never put Access `Location` query strings, API keys, or service tokens in logs or reports.

## 5. Offline preparation: machine-readable drift evidence

Generate a sanitized JSON report without requiring TrueNAS access. Each service
must keep *intent*, *observation* and *inference* separate.

Suggested record:

```json
{
  "service_id": "garage-admin",
  "expected_external": false,
  "origin_port": 3903,
  "layers": {
    "public_dns": {"status": "unknown", "evidence": null},
    "cloudflare_tunnel": {"status": "unknown", "evidence": null},
    "cloudflare_access": {"status": "observed", "source": "outside_in", "observed_at": "2026-10-17T11:00:00Z", "http_status": 302},
    "pfsense_nat_haproxy": {"status": "unknown", "evidence": null},
    "traefik": {"status": "unknown", "evidence": null},
    "outside_in_origin": {"status": "unknown", "evidence": null}
  },
  "exposure_assessment": "requires_review",
  "origin_anonymously_accessible": null
}
```

**Rules for automation:**
- `unknown` is never converted into `matched` or `drift`.
- A public Access redirect on a private-intent hostname is an **edge route
  review finding**, not proof of an origin bypass.
- Report a confirmed policy drift only when an authoritative active route or
  outside-in observation demonstrates unwanted exposure; retain the evidence
  source, timestamp, and freshness.
- For a private API, even an authenticated public route should be flagged
  for removal review; authentication does not change `external=false`.
- Do not follow redirects to login endpoints or store signed `Location` query
  parameters, cookies, bearer tokens or Cloudflare service-token values.
- Make every probe bounded (timeout, concurrency and retries), passive by
  default, and avoid destructive or authenticated mutations.
- Reconcile against the `nabla-compose` catalog revision and record that
  revision explicitly; if unavailable, report `catalog_revision=unknown`.

## 6. Cross-repository probe priority migration contract

The source of authority is `nabla-compose/catalog/homelab-exposure-overrides.json`.
An optional integer `probePriority` expresses ascending priority; absence
means ordinary rotating eligibility. The three Garage entries should receive
ranks 0, 1 and 2. Do not infer priority from `criticality`, and do not enable
public probing for `external=false` services.

Acceptance sequence:
1. Publish the schema and catalog field in `nabla-compose`, with validation
   for integer types, uniqueness where required, and non-negative values.
2. Extend `HomelabService` with alias `probePriority` and propagate it from
   exposure overrides in `fastapi-sample`.
3. Use catalog priority in the sampler, keeping the current bootstrap ordering
   only when no published priority is present.
4. Assert Garage inclusion, fair rotation of unrelated services, stable
   `rotated_priority_ids`, and unchanged public/internal probe eligibility.
5. Run focused unit/contract tests and the full offline quality gate at the
   exact commit SHA before considering the PR ready.

No live Cloudflare, TrueNAS, pfSense, or Traefik changes are authorized by
this preparation. Keep the PR open and do not merge automatically.

## 7. Run the offline reconciliation

Save a sanitized declared catalog in `declared.json` as
`{"catalog_revision":"<full-sha>","services":[{"id":"garage-admin","external":false}]}`.
Save independently verified observations in `observed.json`:

```json
{
  "observations": [
    {
      "service_id": "garage-admin",
      "layers": {
        "cloudflare_access": {"status": "observed", "source": "outside_in", "observed_at": "2026-10-17T11:00:00Z", "http_status": 302}
      }
    }
  ]
}
```

Then run from the repository root (no network or secrets required):

```bash
python scripts/audit/garage_exposure_drift.py \
  --declared declared.json --observed observed.json \
  --output garage-exposure-report.json \
  --as-of 2026-10-17T12:00:00Z --max-age-hours 24
python -m pytest -q tests/unit/test_garage_exposure_drift.py
```

A `requires_review` finding does not prove anonymous origin access. A
`confirmed_drift` finding requires an explicit `drift` status from an
independently verified layer. The utility deliberately does **not** discover
Cloudflare configurations or infer endpoint reachability. Collect those
observations separately with approved read-only credentials.

**Validation status (2026-10-17):** 15 offline drift tests and 14
deployment-unit planner tests passed in an isolated Python 3.13 environment.
The published Git blob SHAs matched the files used for those tests. The full
repository checkout, locked dependency set, Ruff/Black and complete local
quality gate remain **NOT_RUN/BLOCKED** because GitHub DNS is unavailable in
the isolated runner. No CI green claim or live exposure validation is made.
Do not mark the release acceptance complete without an exact-HEAD run.


### Evidence integrity (strict offline contract)

All `matched`, `observed` and `drift` records must carry an
`observed_at` ISO-8601 timestamp with timezone and an enumerated `source`:

| Layer | Accepted source |
| --- | --- |
| `public_dns` | `dns_lookup` |
| `cloudflare_tunnel` | `cloudflare_api` |
| `cloudflare_access` | `cloudflare_api` or `outside_in` |
| `pfsense_nat_haproxy` | `pfsense_config` |
| `traefik` | `traefik_config` |
| `outside_in_origin` | `outside_in` |

The examples above are **synthetic test fixtures**, not evidence that the
October 15 redirect is still live. The default evidence window is 24 hours;
older observations and timestamps more than five minutes into the future
become `unknown`. Missing source or timezone raises an error rather than
fabricating a confirmed finding. Use `--as-of` for reproducible offline
replay only, not to conceal stale observations in current reports.

This is a **source classification, not cryptographic attestation**. The
operator must independently validate each input against read-only
Cloudflare API configuration, pfSense/Traefik state or trusted outside-in
measurements. The script cannot verify authenticity of hand-written JSON.
A `confirmed_drift` means confirmed *against the provided sourced metadata*,
not that anonymous origin access is established. Never interpret
`no_confirmed_drift` as proof of safety.

## 8. Prepare unit-aware probes without network access

The normalized unit metadata proposed in
[nabla-compose PR #257](https://github.com/AlbanAndrieu/nabla-compose/pull/257)
is **not yet exported by its canonical catalog generator**. The FastAPI preview
therefore does not mutate the existing production sampler.

From the repository checkout, preview candidate internal and public units:

```bash
python nabla/api/homelab_probe_units.py \
  --catalog nabla/api/data/homelab-services.json \
  --observer internal --limit 12 --cycle 0

python nabla/api/homelab_probe_units.py \
  --catalog nabla/api/data/homelab-services.json \
  --observer public --limit 12 --cycle 0

python -m pytest -q tests/unit/test_homelab_probe_units.py
```

The preview is intentionally **dry-run only** (`execution_performed=false`).
Without `deploymentUnitId` metadata, services are separate units. With an
explicit Garage `deploymentUnitId=truenas:garage`, they share one scheduling
selection while retaining three endpoint identities. A unit is not an
unbounded request budget: primary probing, conditional secondaries, TTL,
cooldown, authentication prerequisites and per-unit singleflight still need
runtime implementation and a separately capped HTTP request budget.

The public observer filters out `external=false` components even inside a
mixed unit. If its declared primary endpoint is private, the dry-run leaves
that primary unavailable rather than silently probing it. Secondary entries
are **descriptions of future conditional checks**, never automatically
executed by the preview. Publish canonical `probePolicy` and acceptance tests
in `nabla-compose` before connecting this planner to the health board.

Validation note: targeted tests passed in an isolated Python environment for
the exact file blob SHA values committed in #342; full application tests,
Black/Ruff and local production-fidelity quality gate remain unverified until
an immutable repository checkout with locked dependencies is available.
