# Cloudflare Tunnel read-only audit

`nabla.api.cloudflare_tunnels` observes Cloudflare read-only state while
`nabla.api.homelab_exposure_audit` compares it with the reviewed `HomelabCatalog` exposure policy.
Cloudflare remains observed state; `HomelabService.external` remains desired state and is never
mutated from runtime observations.

## Runtime endpoint

The comparison is exposed at:

```text
GET /api/homelab/exposure-audit
```

The endpoint reports:

- `MATCH`: desired and observed Cloudflare exposure agree;
- `UNEXPECTEDLY_EXPOSED`: Cloudflare routes a hostname that should not be exposed, or a hostname is
  observed that is not managed by the FastAPI exposure catalog;
- `MISSING_EXPOSURE`: `external=true` but no matching remotely managed Cloudflare ingress exists;
- `UNKNOWN`: the absence of exposure cannot be established safely, for example because a tunnel uses
  local configuration.

Direct WAN endpoints on non-standard ports, such as `home.albandrieu.com:10443`, are intentionally
excluded from the Cloudflare-hostname comparison. They are audited separately by `/sickz` WAN policy.

## Python SDK

Use Cloudflare's official `cloudflare` Python package (5.x). The project installs the SDK as a runtime
dependency. The observer is still loaded only when the integration is configured.

## Credentials

Configure only a scoped API token, never the Global API Key:

```text
CLOUDFLARE_ACCOUNT_ID=<account id>
CLOUDFLARE_API_TOKEN=<scoped read-only token>
```

The token should have the minimum Cloudflare Tunnel read permission needed to list tunnels and read
their configurations. Do not grant Tunnel Write.

If either environment variable is absent, the audit returns `status=disabled` and performs no
Cloudflare network request. Desired hostname findings are reported as `UNKNOWN` rather than assuming
that missing credentials mean missing exposure.

## What is observed

For each active Cloudflared tunnel, the observer records:

- tunnel ID and name;
- tunnel health/status;
- configuration source (`cloudflare` or `local`);
- for remotely managed tunnels, each configured public hostname and its origin service.

Catch-all ingress rules without a hostname are ignored because they do not represent a public
hostname.

Locally managed (`config_src=local`) tunnel ingress cannot be reconstructed reliably from the remote
configuration endpoint. If any such tunnel is present, an absent hostname is therefore `UNKNOWN`, not
`MISSING_EXPOSURE` or a false `MATCH`.

## Security invariant

```text
FastAPI exposure catalog              Cloudflare observed state
external=true/false                   hostname -> origin
          |                                  |
          +---------------+------------------+
                          v
                    exposure audit
```

The comparison fails closed: TrueNAS discovery, DNS resolution, HTTP reachability, a stored
`tunnelUrl`, or Cloudflare observations must never automatically change a service to `external=true`.
An observed hostname that is absent from the catalog is itself reported as unexpected exposure.
