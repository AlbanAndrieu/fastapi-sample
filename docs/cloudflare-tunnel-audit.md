# Cloudflare Tunnel read-only audit

`nabla.api.cloudflare_tunnels` prepares a read-only observer for the homelab exposure audit.
It is intentionally separate from the desired `HomelabCatalog`: Cloudflare is observed state,
while `HomelabService.external` remains reviewed desired state.

## Python SDK

Use Cloudflare's official `cloudflare` Python package (5.x). The observer intentionally loads it
lazily so deployments without Cloudflare audit credentials perform no Cloudflare import or network
request.

When enabling the integration, install the SDK with `uv` and regenerate `uv.lock`:

```bash
uv add --group cloudflare 'cloudflare>=5.6.0,<6'
```

The package is not added to `pyproject.toml` in this preparation PR because the execution environment
used to create the PR cannot reach PyPI to regenerate `uv.lock`. Do not merge a dependency change with
a stale lock file.

## Credentials

Configure only a scoped API token, never the Global API Key:

```text
CLOUDFLARE_ACCOUNT_ID=<account id>
CLOUDFLARE_API_TOKEN=<scoped read-only token>
```

The token should have the minimum Cloudflare Tunnel read permission needed to list tunnels and read
their configurations. Do not grant Tunnel Write.

If either environment variable is absent, `observe_cloudflare_tunnels()` returns an empty list and
performs no network request.

## What is observed

For each active Cloudflared tunnel, the observer records:

- tunnel ID and name;
- tunnel health/status;
- configuration source (`cloudflare` or `local`);
- for remotely managed tunnels, each configured public hostname and its origin service.

Catch-all ingress rules without a hostname (for example an HTTP 404 fallback) are ignored because
they do not represent a public hostname.

Locally managed (`config_src=local`) tunnel ingress cannot be reliably reconstructed from the remote
configuration endpoint. The observer therefore reports the tunnel but leaves its ingress unknown
instead of guessing that it is safe.

## Intended next phase

The observer will later be compared against the desired homelab catalog:

```text
HomelabCatalog desired state          Cloudflare observed state
external=true/false                   hostname -> origin
          |                                  |
          +---------------+------------------+
                          v
                    exposure audit
```

Useful finding states will be:

- `MATCH`: desired and observed exposure agree;
- `UNEXPECTEDLY_EXPOSED`: Cloudflare routes a hostname for a service whose desired `external` is false;
- `MISSING_EXPOSURE`: desired `external` is true but no matching Cloudflare route is observed;
- `UNKNOWN`: exposure cannot be established safely, for example a locally managed tunnel.

This comparison must fail closed: TrueNAS discovery, DNS resolution, HTTP reachability, or a stored
`tunnelUrl` must never automatically change a service to `external=true`.
