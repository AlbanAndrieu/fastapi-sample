# MCP integrations

This repository keeps MCP integrations least-privileged by default. Secrets must stay outside the repository.

## FastAPI sample

The application exposes the project-local MCP server at:

```text
http://127.0.0.1:8080/mcp
```

Use the local server when the agent runs on the workstation/LAN. For runtime status rather than MCP tools, follow `.agents/skills/fastapi-cloud/SKILL.md`, which uses local HTTP health endpoints first and FastAPI Cloud as fallback.

## GitHub

Use GitHub's official remote MCP server in read-only mode:

```text
https://api.githubcopilot.com/mcp/x/all/readonly
```

This deliberately prevents MCP-side mutations while still allowing repository, pull-request, issue, workflow, and Actions inspection. Use the native GitHub integration of the current agent when one is already available; do not duplicate calls through MCP unnecessarily.

OpenCode OAuth:

```bash
opencode mcp auth github
opencode mcp debug github
```

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

## pfSense

The OpenCode config includes `pfsense-auditor` but leaves it disabled by default. It uses the security-focused `pfsense-mcp-server` Auditor profile, which exposes read tools and no write tools by default.

Before enabling it, configure these variables in the local shell or secret manager, never in Git:

```text
PFSENSE_API_URL
PFSENSE_IDENTITY
PFSENSE_API_KEY_FILE
```

`PFSENSE_API_KEY_FILE` must point to an owner-readable key file outside the repository. Keep TLS verification strict. Optionally reduce the tool surface with `PFSENSE_ALLOWED_TOOLS`.

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
