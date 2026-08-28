# MCP integrations

This repository keeps MCP integrations least-privileged by default. Secrets must stay outside the repository.

## FastAPI sample

The application exposes the project-local MCP server at:

```text
http://127.0.0.1:8080/mcp
```

Use the local server when the agent runs on the workstation/LAN. For runtime status rather than MCP tools, follow `.agents/skills/fastapi-cloud/SKILL.md`, which uses local HTTP health endpoints first and FastAPI Cloud as fallback.

### Local runtime devtools

The local FastAPI MCP also exposes a small runtime-debug surface inspired by the built-in Next.js development MCP model. It does not require a second MCP process or access to the Docker socket: the running Python process captures a bounded in-memory ring buffer and exposes it through the same `/mcp` server.

The runtime tools are:

- `get_runtime_metadata` — process/Python/version metadata and log-buffer state;
- `get_runtime_logs` — bounded recent logs with level/text filtering;
- `get_runtime_errors` — bounded ERROR/CRITICAL events for an agent debugging loop.

They are automatically registered when the development server is started with `--reload`, which is already how `make up` and `make up-uvicorn` run locally. Override explicitly when needed:

```bash
RUNTIME_DIAGNOSTICS_ENABLED=false make up
RUNTIME_DIAGNOSTICS_ENABLED=true make up
```

Security properties:

- the tools are not registered in a normal production process without `--reload`;
- `RUNTIME_DIAGNOSTICS_ENABLED=false` always disables them;
- direct `/v1/runtime/*` HTTP access is restricted to loopback clients even though the development server itself binds on `0.0.0.0`;
- the buffer is bounded and process-local (local development defaults to one worker);
- the existing application redactor plus bearer-token masking runs before events are returned;
- message and exception sizes are bounded;
- there is no MCP tool that clears, writes, executes commands, or reads arbitrary files.

## GitHub

OpenCode 1.18.x cannot authenticate against the official remote GitHub MCP endpoint because that OAuth server does not support the Dynamic Client Registration flow expected by OpenCode. The shared OpenCode configuration therefore uses GitHub's **official local MCP server** in Docker instead of the remote endpoint.

Authentication is resolved at process start from either:

1. `GITHUB_PERSONAL_ACCESS_TOKEN`, if already exported; or
2. `gh auth token`, using the existing GitHub CLI login.

The token is passed to the container through its environment and is never stored in this repository or inserted literally into Docker command arguments.

The server is forced into read-only mode and limited to the toolsets needed for repository/PR/CI/security inspection:

```text
context,repos,pull_requests,issues,actions,code_security
```

Check it with:

```bash
gh auth status
opencode mcp list
```

`opencode mcp auth github` is intentionally no longer required for this local-server configuration.

Use the native GitHub integration of the current agent when one is already available; do not duplicate calls through MCP unnecessarily.

## Vercel

Use Vercel's official remote MCP server:

```text
https://mcp.vercel.com
```

OpenCode OAuth:

```bash
opencode mcp auth vercel
opencode mcp debug vercel
```

Prefer it for project/deployment/log inspection instead of scraping dashboard pages.

## Sentry

Use Sentry's official stdio MCP server for the self-hosted instance. The shared configuration points it at:

```text
sentry.albandrieu.com
```

It is intentionally disabled by default in `opencode.json`. Create a dedicated **User Auth Token** in the self-hosted Sentry instance, keep it outside Git, then export it before enabling the server locally:

```bash
export SENTRY_ACCESS_TOKEN='...'
```

The shared command uses only the read-oriented `inspect` skill and disables the MCP process's own upstream Sentry telemetry:

```bash
npx -y @sentry/mcp-server@latest \
  --host=sentry.albandrieu.com \
  --skills=inspect \
  --sentry-dsn=
```

For inspection, grant only the minimum scopes supported by the installed Sentry MCP/server version, normally `org:read`, `project:read`, `team:read`, and `event:read`. Do not grant project/team write scopes unless an explicitly reviewed project-management operation requires them.

The application DSN (`SENTRY_DSN`) and the MCP API token (`SENTRY_ACCESS_TOKEN`) are different credentials and must remain independently rotatable.

## pfSense

The OpenCode config includes `pfsense-auditor` but leaves it disabled by default. It uses the security-focused `pfsense-mcp-server` Auditor profile, which exposes read tools and no write tools by default.

Before enabling it, configure these variables in the local shell or secret manager, never in Git:

```text
PFSENSE_API_URL
PFSENSE_IDENTITY
PFSENSE_API_KEY_FILE
```

`PFSENSE_API_KEY_FILE` must point to an owner-readable key file outside the repository. Keep TLS verification strict. Optionally reduce the tool surface with `PFSENSE_ALLOWED_TOOLS`.

The FastAPI application's own pfSense observer is separate and uses `PFSENSE_API_KEY` in the `X-API-Key` header. Do not reuse or confuse that credential with `TRUENAS_API_KEY`.

After configuration, set `pfsense-auditor.enabled` to `true` in a local OpenCode override, or run the server directly for testing:

```bash
uvx --from pfsense-mcp-server==0.5.1 pfsense-mcp-server
```

Do not opt into the `write_protected` profile unless an explicit change operation is required and reviewed.

## TrueNAS

Do **not** enable `truenas/truenas-mcp` in the shared project configuration yet.

Reasons:

- it is published as a research preview;
- it includes management/write capabilities;
- its current public connection documentation still describes legacy-style `:443/websocket` behavior;
- this homelab currently requires TrueNAS 26 JSON-RPC at `/api/current` and a version-matched official `truenas/api_client`.

For now, use the `fastapi-sample` MCP/HTTP health layer as the read-only TrueNAS abstraction. Direct appliance diagnostics should use the official TrueNAS API client with the server-compatible release and credentials held outside Git.

A future dedicated TrueNAS MCP should wrap the same official `truenas/api_client` adapter already validated by this project and expose an explicitly read-only toolset.

## FastAPI Cloud

No official FastAPI Cloud MCP server is configured. Use the agent-friendly FastAPI Cloud CLI and `.agents/skills/fastapi-cloud/SKILL.md` instead.

Interactive login:

```bash
fastapi login
fastapi cloud whoami
```

CI/deploy authentication uses a separate deploy token:

```bash
fastapi cloud setup-ci --secrets-only
```

or create a Deploy Token in the FastAPI Cloud dashboard. Never commit `FASTAPI_CLOUD_TOKEN` or `FASTAPI_CLOUD_APP_ID`.
