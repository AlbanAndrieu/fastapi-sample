---
name: fastapi-cloud
description: >-
  Operate and diagnose the fastapi-sample FastAPI Cloud deployment. Use for
  FastAPI Cloud authentication, deploy tokens, environment-variable inventory,
  deployments, runtime logs, and production-vs-local homelab health diagnostics.
---
# FastAPI Cloud operations

Use this skill for FastAPI Cloud runtime and deployment operations. It complements the `fastapi` coding skill; it is not a replacement for FastAPI framework guidance.

## Runtime priority

FastAPI Sample has two production observer scopes plus the developer workstation:

- **TrueNAS homelab production** — preferred for private homelab state when the
  caller is on the trusted LAN:
  - `https://sample.int.albandrieu.com/api`
  - `https://sample.int.albandrieu.com/api/homelab/health`
  - `https://sample.int.albandrieu.com/api/homelab/runtime`
  - `https://sample.int.albandrieu.com/api/homelab/status`
  - direct fallback: `http://172.17.0.24:8091`
- **FastAPI Cloud production** — external/WAN observer:
  - `https://fastapi-sample.fastapicloud.dev/api`
  - `https://fastapi-sample.fastapicloud.dev/api/homelab/health`
  - `https://fastapi-sample.fastapicloud.dev/api/homelab/runtime`
  - `https://fastapi-sample.fastapicloud.dev/api/homelab/status`
- **Local workstation** — development behavior only:
  - `http://127.0.0.1:8080/api`

Prefer the TrueNAS homelab production runtime for TrueNAS, pfSense and
Prometheus observations because it has trusted-LAN reachability. Do not make
FastAPI Cloud an approved LAN administration source merely to reproduce the
same probes externally.

Do not treat failure of one runtime as proof that another runtime is unhealthy.
Record the runtime mode and observer scope actually tested.

## pfSense host configuration source of authority

FastAPI Sample owns the observer behavior, not the complete pfSense appliance
configuration. For current Netgate 1100 sizing, PHP-FPM limits, memory incidents,
Snort/pfBlockerNG/Unbound budgets and supported recovery procedures, consult
`AlbanAndrieu/nabla-compose`, especially:

- `docs/pfsense-php-fpm-hardening.md`;
- `docs/pfsense-flow-observability-memory.md`;
- `docs/pfsense-diagnose-recover.md`;
- `.agents/skills/pfsense-api-debugging/SKILL.md`.

Do not increase FastAPI probe rate, concurrency or endpoint depth based only on
this repository. Revalidate the appliance constraints in `nabla-compose`
first, particularly after pfSense upgrades.

## CLI execution contract

Always execute the project-pinned FastAPI/FastAPI Cloud CLI through the repository toolchain:

```bash
mise exec -- uv run which fastapi
mise exec -- uv run fastapi --version
```

Do not call a system/global `fastapi` binary and do not install the CLI globally. The expected executable is the repository `.venv/bin/fastapi`. This keeps the CLI version reproducible with `mise`, `uv.lock`, and the project virtual environment.

## Authentication

Interactive user login:

```bash
mise exec -- uv run fastapi cloud login
mise exec -- uv run fastapi cloud whoami
```

`mise exec -- uv run fastapi cloud login` stores an interactive user session. It does **not** create `FASTAPI_CLOUD_TOKEN`.

For automation/CI, use a FastAPI Cloud **Deploy Token**. Create it in the FastAPI Cloud dashboard under the app's **Deploy Tokens**, or use:

```bash
mise exec -- uv run fastapi cloud setup-ci --secrets-only
```

The deploy token is shown only when created/regenerated. Never commit it. Prefer GitHub Actions secrets, a password manager, or another local secret store.

Expected automation variables:

```text
FASTAPI_CLOUD_TOKEN
FASTAPI_CLOUD_APP_ID
```

## Environment inventory

List application environment variables after authenticating/linking the project:

```bash
mise exec -- uv run fastapi cloud env list
```

Do not copy secret values into issues, PRs, logs, or chat. When diagnosing configuration drift, compare variable **names and presence** whenever possible.

Canonical application-observer credentials are intentionally separate from
infrastructure automation credentials:

```text
TRUENAS_API_USERNAME=fastapi_observer
TRUENAS_API_KEY
PFSENSE_POSTURE_API_KEY
PFSENSE_SECURITY_API_KEY
CLOUDFLARE_API_TOKEN
```

Do not use `TRUENAS_INFRA_API_USERNAME` or `TRUENAS_INFRA_API_KEY` in the
FastAPI runtime. Those names belong to OpenTofu/Terragrunt in
`nabla-compose`. Likewise, `TRUENAS_MCP_API_KEY` belongs to the MCP launcher
and is not a FastAPI fallback.

The two pfSense identities intentionally share transport defaults while keeping credentials separate:

```text
PFSENSE_API_URL=https://home.albandrieu.com:10443
PFSENSE_API_VERIFY_SSL=true
PFSENSE_POSTURE_API_KEY=<dedicated posture GET-only key>
PFSENSE_POSTURE_API_VERIFY_SSL=true
PFSENSE_SECURITY_API_KEY=<dedicated diagnostics-table GET-only key>
PFSENSE_SECURITY_API_VERIFY_SSL=true
PFSENSE_SECURITY_PATH_MODE=shared_wan
PFSENSE_AUTHENTICATED_PROBES_ENABLED=true
```

`PFSENSE_POSTURE_API_URL`, `PFSENSE_POSTURE_API_VERIFY_SSL`, `PFSENSE_SECURITY_API_URL`, and `PFSENSE_SECURITY_API_VERIFY_SSL` are optional overrides when an identity uses a different transport. The production deploy workflow pins both per-identity TLS overrides to `true` so stale Cloud values cannot silently disable certificate verification. `PFSENSE_API_KEY` is obsolete and is no longer consumed by FastAPI Sample. It was removed from FastAPI Cloud on 2026-09-02; remove it from homelab runtime secrets as well.

FastAPI Cloud keeps authenticated pfSense posture and security probes enabled
in steady state now that both dedicated least-privilege keys are valid. The
posture observer fails fast on the first HTTP 401, so one rejected key cannot
fan out across deeper pfREST reads and amplify Login Protection / `sshguard`.

The production deploy workflow sets
`PFSENSE_AUTHENTICATED_PROBES_ENABLED=true` declaratively. Use `false` only
as an emergency kill-switch during credential rotation or a fresh Login
Protection incident, then restore `true` after the key/path issue is corrected.
Keep the checked-in deployment contract and FastAPI Cloud environment aligned;
do not permanently whitelist an ephemeral Cloud egress.

Provider health must validate that its canonical credential exists before attempting provider authentication. A missing credential is configuration health data, not a generic network failure. Never substitute one provider's key for another provider or recommend collapsing the dedicated pfSense identities back into one shared secret.

For pfSense liveness, use the posture identity and the lightweight endpoint:

```text
GET /api/v2/system/version
```

Do not use `/api/v2/status/system` as the synchronous liveness gate; it collects substantially more live system information and can exceed a short health timeout. The security identity should only read:

```text
GET /api/v2/diagnostics/table?id=snort2c
```

### Updating a FastAPI Cloud secret

Set or replace a secret interactively without putting its value on the command line:

```bash
mise exec -- uv run fastapi cloud env set --secret TRUENAS_API_KEY
```

After changing an application environment variable, redeploy before validating the running application:

```bash
mise exec -- uv run fastapi deploy
```

Treat `env set` and runtime deployment as two distinct steps. A successful `env set` proves only that the application configuration was updated; the runtime check is authoritative only after the new deployment is ready.

For a negative credential test, temporarily remove the canonical variable, deploy, and require an explicit sanitized result such as `phase=authentication stage=missing_api_key`. Restore the secret with `env set --secret`, redeploy, then require Authentication and API stages to recover. Never paste the secret into test fixtures, logs, PR descriptions, or diagnostic output.

## Optional integrations

Unleash/GitLab is an optional feature-flag control plane. DNS, TLS, timeout, registration, or availability failures from Unleash must never block application construction or the FastAPI Cloud startup/verification path. Keep remote flag evaluation off the critical startup path and report failures as warning/observability evidence only.

## Runtime logs

Recent logs:

```bash
mise exec -- uv run fastapi cloud logs . --tail 200 --since 2h --no-follow
```

TrueNAS diagnostics:

```bash
mise exec -- uv run fastapi cloud logs . --tail 500 --since 2h --no-follow \
  | grep -E 'TrueNAS (API|runtime)|proxy_route=|phase=|stage='
```

Interpret the TrueNAS fields independently:

- `phase=connect`: failure happened before API authentication.
- `phase=authentication`: transport succeeded; credentials/auth negotiation failed.
- `phase=call`: authentication succeeded; the JSON-RPC call failed.
- `proxy_route=direct`: no environment proxy selected.
- `proxy_route=proxy_candidate`: a proxy variable can affect the WebSocket client.
- `proxy_route=bypass`: a proxy exists but `NO_PROXY` bypasses it for TrueNAS.

Never log API keys, proxy URLs containing credentials, or token values.

## Deployment verification diagnostics

FastAPI Cloud can report a deployment as `verification failed` while a later replica restart is live. Treat these as separate facts, not a contradiction.

When this occurs:

1. capture the deployment ID from bounded JSON logs;
2. find the first `Application startup failed` and its root traceback;
3. find any later `Application startup complete` for the same deployment ID;
4. distinguish a transient startup dependency failure (DNS/database/provider) from an application build failure;
5. compare the runtime release version with `pyproject.toml`, but do not claim an exact Git SHA is deployed unless the runtime exposes immutable revision evidence.

Useful command:

```bash
mise exec -- uv run fastapi cloud logs . \\
  --no-follow --tail 500 --since 2h --json
```

A public `live` response proves the current replica serves traffic. It does not retroactively turn the original deployment verification into success.

FastAPI Cloud also injects `FASTAPICLOUD_DEPLOYMENT_ID` automatically. Use it to correlate replicas and logs. This project additionally stamps the checked-out Git SHA as `BUILD_REVISION`; `/v2/version` exposes it as `build_revision` so production acceptance can prove the exact immutable revision rather than only the semantic release version.

## Startup dependency diagnostics

PostgreSQL is traffic-critical. A PostgreSQL startup failure must remain fatal, but logs must classify the failing stage without printing credentials:

- `phase=dns stage=name_resolution`: resolver/provider problem before TCP;
- `phase=connect stage=connection_refused|timeout`: transport path;
- `phase=tls stage=tls_error`: encrypted connection negotiation;
- `phase=authentication stage=credentials`: PostgreSQL authentication;
- `stage=database_schema`: connection succeeded and schema/model initialization failed.

Correlate these records with `FASTAPICLOUD_DEPLOYMENT_ID` and `BUILD_REVISION`. Do not treat optional Unleash/GitLab failures as part of this critical chain.

## Deployment workflow

Production deploys are validated by `.github/workflows/deploy.yml` before the FastAPI Cloud deploy command runs. When production appears stale:

1. Check the current `master` commit.
2. Check the `Deploy to FastAPI Cloud` GitHub Actions workflow for that commit.
3. Distinguish validation failure from FastAPI Cloud deployment failure.
4. Only inspect FastAPI Cloud runtime logs after confirming the expected commit actually deployed.

A successful public HTTP `/api` response does not prove WebSocket JSON-RPC health. Use `/api/homelab/health`, `/api/homelab/runtime`, and runtime logs for TrueNAS.

## TrueNAS runtime contract

The FastAPI application is the preferred read-only abstraction for TrueNAS runtime checks. Current TrueNAS v26 JSON-RPC uses `/api/current`; do not add REST fallbacks or legacy `/websocket` assumptions.

For direct appliance debugging, use the TrueNAS client/version that matches the server release and keep credentials outside the repository.

## Completion gate

An agent must not declare FastAPI Cloud, homelab-runtime, deployment, or diagnostic work complete while a known residual, deferred validation, limitation, cross-repository follow-up, or unresolved risk is not recorded in `docs/engineering-roadmap.md`.

Before reporting completion, reconcile the observed runtime evidence with the roadmap and record the next acceptance proof for every remaining item. CI green or basic reachability alone does not waive this requirement. Keep transport reachability, authentication, application acceptance, freshness, and observer confidence distinct when they differ.
