---
name: fastapi-cloud
description: Operate and diagnose the fastapi-sample FastAPI Cloud deployment. Use for FastAPI Cloud authentication, deploy tokens, environment-variable inventory, deployments, runtime logs, and production-vs-local homelab health diagnostics.
---

# FastAPI Cloud operations

Use this skill for FastAPI Cloud runtime and deployment operations. It complements the `fastapi` coding skill; it is not a replacement for FastAPI framework guidance.

## Runtime priority

For homelab/runtime status, prefer the local application when the agent is on the LAN:

1. `http://127.0.0.1:8080/api`
2. `http://127.0.0.1:8080/api/homelab/health`
3. `http://127.0.0.1:8080/api/homelab/runtime`
4. `http://127.0.0.1:8080/api/homelab/status`

If the local endpoint is unavailable because the agent is outside the LAN or the local app is not running, use the production fallback:

1. `https://fastapi-sample.fastapicloud.dev/api`
2. `https://fastapi-sample.fastapicloud.dev/api/homelab/health`
3. `https://fastapi-sample.fastapicloud.dev/api/homelab/runtime`
4. `https://fastapi-sample.fastapicloud.dev/api/homelab/status`

Do not treat a failed local probe as evidence that production is unhealthy. Record which runtime was actually tested.

## Authentication

Interactive user login:

```bash
fastapi login
fastapi cloud whoami
```

`fastapi login` stores an interactive user session. It does **not** create `FASTAPI_CLOUD_TOKEN`.

For automation/CI, use a FastAPI Cloud **Deploy Token**. Create it in the FastAPI Cloud dashboard under the app's **Deploy Tokens**, or use:

```bash
fastapi cloud setup-ci --secrets-only
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
fastapi cloud env list .
```

Do not copy secret values into issues, PRs, logs, or chat. When diagnosing configuration drift, compare variable **names and presence** whenever possible.

## Runtime logs

Recent logs:

```bash
fastapi cloud logs . --tail 200 --since 2h --no-follow
```

TrueNAS diagnostics:

```bash
fastapi cloud logs . --tail 500 --since 2h --no-follow \
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
