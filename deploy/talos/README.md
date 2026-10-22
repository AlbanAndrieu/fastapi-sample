# Talos / TrueNAS staging — deployment preparation

This is an **opt-in, internal-only** staging workload. Production remains
`https://fastapi-sample.fastapicloud.dev`. It is not an automatic cutover
from the TrueNAS Docker staging at `172.17.0.24:8091`.

## Preconditions (not performed by this PR)

1. Confirm Talos node readiness (172.17.0.50/.51/.52), CNI NetworkPolicy
   enforcement, in-cluster DNS, registry pull access and runtime storage needs.
2. Build the existing multi-stage Dockerfile offline/local-first, scan the
   image, push to an approved registry **without GitHub Actions**, and replace
   `REPLACE_WITH_VERIFIED_IMAGE_DIGEST` with the exact 64-hex SHA-256 digest.
   The placeholder deliberately prevents accidental deployment.
3. Provision the **required** `fastapi-sample-runtime-secrets` through the approved private
   secret mechanism (prefer a secrets operator with encrypted GitOps source).
   Do **not** commit tokens, passwords or generated Secret manifests.
   Secrets can include DIAGNOSTICS_ACCESS_KEY, owner identity and private
   LiteLLM credentials only when their intended integrations are validated.
4. Confirm `HOMELAB_TRUSTED_CIDRS=82.66.4.247/32` reflects the **real client
   source**, not Kubernetes pod/ingress addresses. Owner diagnostics must
   retain their independent signed identity check; do not trust arbitrary
   `X-Forwarded-For`. Populate `HOMELAB_TRUSTED_PROXY_CIDRS` only for verified
   proxy hop CIDRs.
5. Make an explicit, audited network policy exception for the *specific*
   Traefik controller namespace/pod labels before exposing the internal
   Service via an authorized private Ingress. The provided policy allows
   ingress from same-namespace pods only. No LoadBalancer, NodePort, public
   Ingress, DNS or Cloudflare route is created. Egress remains unrestricted
   until all health-probe dependencies are enumerated.

## Validation (only after runtime approval)

- Offline: `python -m pytest -q tests/unit/test_talos_manifest_contract.py`;
  `kubectl apply --dry-run=client -f deploy/talos/fastapi-sample.yaml`
  (substitute the image digest first).
- Policy: test ingress denied from an unrelated namespace and permitted from
  the approved private Traefik workload after adding an explicit exception.
- Runtime: verify one Ready pod, `/health`, Service DNS, restart stability
  and no public path to diagnostics/MCP; verify missing owner credentials
  produce 403, while the **explicit public DTO** remains non-sensitive.
- Observability: verify Gatus/Prometheus/pg exporter/pfSense evidence across
  three probe cycles, not just a pod-ready signal; distinguish unknown from
  unhealthy. Confirm Garage Web UI and Gatus catalog entries.
- Rollback: do not re-route public production. Scale down or remove the
  staging Deployment; the original TrueNAS staging stays independent.

## Known limits

- Root filesystem is **not yet read-only**: application temp/cache paths need
  verification before enabling it.
- No PVC: this is intentionally stateless; any required persistence must be
  specified and tested rather than silently falling back to pod storage.
- Image is intentionally unusable until a digest is supplied.
- Startup health does not prove all external/LAN dependencies are healthy.
- Quality gate and actual Talos deployment: **NOT_RUN**.
- The live FastAPI Cloud production app deploys directly, never from a GitHub Actions workflow. This staging manifest is not connected to that deployment.
