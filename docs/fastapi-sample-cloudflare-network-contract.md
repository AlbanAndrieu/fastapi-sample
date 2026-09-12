# FastAPI Sample Cloudflare and workstation network contract

This document defines the read-only Cloudflare objects and workstation network
paths that the FastAPI Sample health board is expected to observe. It is an
operator contract, not a source of credentials.

## Project-scoped Cloudflare objects

FastAPI Sample deliberately ignores unrelated account-wide reusable policies
and Service Tokens when computing this project's control-plane status.

| Object | Canonical value | Meaning |
| --- | --- | --- |
| Reusable Access policy | `fastapi-sample-monitor` | Machine-access policy used by the FastAPI Sample observer. |
| Access Service Token | `fastapi-sample-monitor` | Machine identity expected by the observer's Service Auth checks. |
| Development/workstation Tunnel | `nabla-albandrieu` | Routes owned by the workstation/development environment. |
| Production Tunnel | `nabla-truescale` | Default production/homelab Cloudflare Tunnel. |

The policy/token names can be overridden for another installation with
`CLOUDFLARE_PROJECT_ACCESS_POLICY_NAME` and
`CLOUDFLARE_PROJECT_SERVICE_TOKEN_NAME`. Their defaults remain
`fastapi-sample-monitor`.

The Cloudflare observer uses the official SDK first for Tunnel and Access
application inventory. If the SDK rejects an otherwise valid read-only request,
the health board falls back to bounded HTTPS GET requests against the same
Cloudflare v4 endpoints. This specifically avoids interpreting an SDK
`BadRequestError` as a credential or service outage when the REST API is
healthy.

The project control-plane policy and Service Token inventory uses the bounded
REST path and filters the returned account objects by the canonical project
name before counts/status are published. Other policies and tokens do not
contribute to FastAPI Sample's status.

No token secret, API token, Client Secret, or raw Authorization header may be
returned by the health API or logged by the observer.

## Tunnel environment invariant

Tunnel ownership is an observed deployment signal:

- `nabla-albandrieu` implies `development`;
- `nabla-truescale` implies `production` by default.

A service declared as production but observed on `nabla-albandrieu` is a
configuration mismatch. The topology health overlay must show a warning rather
than silently treating the workstation Tunnel as production. The inverse
mismatch is also reported.

Tunnel environment is not inferred when the Tunnel name is unknown. Unknown
Tunnel names remain neutral until they are explicitly mapped.

## Workstation DNS and network path semantics

The application does not shell out to `dig` as part of normal HTTP/TCP probes.
Configuration is loaded through environment variables (for example with
`os.getenv`), while HTTP clients and `asyncio.open_connection()` use the
runtime/OS resolver implicitly.

This distinction matters when reading the flow graph: a hostname can resolve
through pfSense/Unbound while the eventual destination is Cloudflare, the
pfSense WAN address, or a direct LAN address.

### `sample.albandrieu.com`

On the workstation, `sample.albandrieu.com` resolves to Cloudflare anycast
addresses. The workstation routes those addresses through its default gateway
(`172.17.0.1`) and reaches the Cloudflare edge. A `302` to the Cloudflare Access
login page plus the `Cloudflare-Access` authentication challenge confirms that
Access is in the path.

That path is therefore:

```text
workstation -> pfSense default gateway -> Internet/Cloudflare edge
            -> Cloudflare Access -> Cloudflare Tunnel -> origin
```

It is **not** pfSense NAT reflection back to the local origin.

### `truenas.albandrieu.com:7000`

The pfSense/Unbound answer for `truenas.albandrieu.com` is the homelab public
WAN address. A workstation request to the hostname/port is therefore the
candidate hairpin path:

```text
workstation -> pfSense WAN address :7000 -> NAT reflection / HAProxy -> TrueNAS
```

Whether reflection/HAProxy was actually selected must be confirmed with the
request to the hostname plus pfSense state/HAProxy evidence. By contrast,
`https://172.17.0.24:7000/` is unambiguously direct LAN and bypasses the WAN
reflection path.

## Operator verification

Check the system resolver and route independently of the application's cached
health evidence:

```bash
getent ahostsv4 sample.albandrieu.com
ip route get "$(getent ahostsv4 sample.albandrieu.com | awk 'NR==1 {print $1}')"

dig +short @172.17.0.1 truenas.albandrieu.com A
ip route get 82.66.4.247
curl -vkI https://truenas.albandrieu.com:7000/
```

`dig @172.17.0.1` is an operator diagnostic against pfSense/Unbound. It is not
the same resolver path as `getent`, which follows the workstation's configured
NSS/system resolver stack. Comparing both is useful evidence and should not be
collapsed into one result.

For Cloudflare inventory, validate only read-only endpoints. Expected minimum
permissions are Tunnel read, Access Apps and Policies read, and Access Service
Tokens read. Do not use write scopes for the health observer.
