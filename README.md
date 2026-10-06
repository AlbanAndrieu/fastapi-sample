# fastapi-sample

FastAPI reference service for REST APIs, MCP/A2A integrations and homelab
observability.

- **Production:** <https://fastapi-sample.fastapicloud.dev>
- **Documentation:** [docs/README.md](docs/README.md)
- **Active roadmap:** [docs/engineering-roadmap.md](docs/engineering-roadmap.md)
- **Incident register:** [docs/incidents.md](docs/incidents.md)

FastAPI Cloud is the canonical production runtime. Automatic Vercel Git
deployments are disabled.

## Requirements

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- [just](https://just.systems/) (available via `mise install just`)
- Node.js 24 + npm 10 for repository tooling
- Docker only for optional local infrastructure

Install repository hooks after cloning:

```bash
mise run hooks
```

## Local development

Install the locked environment and start the API:

```bash
uv sync --frozen
uv run fastapi dev --port 8080
```

Use the complete ASGI entrypoint when testing lifespan, MCP or A2A resources:

```bash
uv run uvicorn server_all:app --reload --host 0.0.0.0 --port 8080
```

Useful local endpoints:

- API docs: <http://127.0.0.1:8080/docs>
- OpenAPI: <http://127.0.0.1:8080/openapi.json>
- health: <http://127.0.0.1:8080/health>
- metrics: <http://127.0.0.1:8080/metrics>
- MCP: <http://127.0.0.1:8080/mcp>

Current entry points and dashboards are documented in
[docs/entrypoints-and-dashboards.md](docs/entrypoints-and-dashboards.md).

## Local task runners

`justfile` is the preferred local-first frontend for routine development and
quality commands, while the existing `Makefile` continues to support legacy
Docker/Sphinx and specialist targets. **Both are retained; removing the
Makefile requires a separate migration decision.**

```bash
mise install just
just --list
just sync
just dev
just test-pfsense
just secrets
just secrets-staged
just fix
just quality
just publish-check
```

`just publish-check` runs the local publication proof; it does **not** publish,
push, deploy or trigger GitHub Actions. For legacy commands continue using
`make <target>`, or use `just make-help`, `just docs`, `just docker-build`,
`just docker-up`, or `just legacy <target>`; those recipes delegate to the
existing `Makefile` rather than duplicating its implementation. `just lint`,
`just format-check`, and `just format` are convenience commands, not a
replacement for the canonical quality gate.

## Secret detection

[Betterleaks](https://github.com/betterleaks/betterleaks) v1.9.0 replaces
Gitleaks in the pre-commit hooks. The `just secrets` recipe scans the local
working tree, and `just secrets-staged` scans staged Git additions. Run
`mise install betterleaks` (or `brew bundle` on a Homebrew environment) to
install the CLI for direct or Just usage. `make just-secrets` delegates to
`just secrets`; the historical Makefile remains available.

MegaLinter already runs `REPOSITORY_BETTERLEAKS` with errors enabled.
The legacy `.gitleaks.toml` and `.gitleaksignore` files are **intentionally
retained**: Betterleaks v1 accepts their rules and existing finding
exclusions. Do not discard or broadly regenerate these exceptions during the
scanner migration. Credential validation/network requests remain off by default.

## Validation

Run focused tests first, then converge the repository quality gate:

```bash
uv run --no-sync pytest -q tests/unit/<relevant-test>.py

bash scripts/agent-quality-gate.sh --fix
bash scripts/agent-quality-gate.sh
```

Before publication, use the canonical clean-tree proof:

```bash
bash scripts/agent-publish.sh
```

The agent gate selects the smallest safe dependency scope:

- `none` for documentation-only changes;
- `quality` for repository/CI contracts;
- `full` for application, runtime, dependency-backed test or unknown changes.

During the explicit no-GitHub-Actions/no-credit mode, local validation is the
merge evidence. Do not dispatch remote workflows merely to replace a missing
local proof.

## Runtime and diagnostics

Health evidence intentionally separates:

1. DNS/TCP/TLS transport;
2. HTTP/API application acceptance;
3. authentication/authorization;
4. workload state;
5. optional provider/telemetry evidence.

Do not infer a global outage from one missing layer.

Start with:

- [documentation index](docs/README.md)
- [incident register](docs/incidents.md)
- [platform diagnostics model](docs/platform-service-diagnostics-model.md)
- [local runtime dependency diagnostic](docs/local-runtime-dependency-report.md)
- [pfSense 502 recovery](docs/pfsense-webconfigurator-recovery.md)
- [Cloudflare/Sentry diagnostics](docs/cloudflare-sentry-runtime-diagnostics.md)

## Observability and integrations

Detailed setup belongs in focused references rather than this README:

- MCP/A2A: [docs/mcp-integrations.md](docs/mcp-integrations.md)
- Cloudflare/Sentry:
  [docs/cloudflare-sentry-runtime-diagnostics.md](docs/cloudflare-sentry-runtime-diagnostics.md)
- health environment:
  [docs/health-monitoring-environment.md](docs/health-monitoring-environment.md)
- public ingress:
  [docs/truenas-public-ingress.md](docs/truenas-public-ingress.md)
- Kubernetes hardening:
  [docs/kubernetes-zero-trust-hardening.md](docs/kubernetes-zero-trust-hardening.md)

Observability integrations are optional. Missing Datadog, Sentry, Logfire,
Cloudflare or Prometheus evidence must not become an application liveness
dependency unless explicitly designed as such.

## Secrets and local configuration

Never commit credentials, tokens, DSNs or decrypted environment files.

Repository agents must not edit `.env`, `.env.local` or `.env.secrets`
unless explicitly requested. Keep SOPS/decrypted material outside commits and
follow the repository policy in [AGENTS.md](AGENTS.md).

## Deployment

FastAPI Cloud is the supported production target. Release/deployment follow-up is
tracked in the [engineering roadmap](docs/engineering-roadmap.md).

Vercel is currently disabled for Git deployments because the Python dependency
graph is not an appropriate Vercel deployment target. The remaining project-side
Git connection is tracked as a roadmap item.

## Documentation policy

The root README is intentionally a quick start, not an operational archive.

- open work → [engineering roadmap](docs/engineering-roadmap.md)
- dated failures → [incident register](docs/incidents.md)
- reusable commands → focused runbooks under `docs/`
- stable architecture/security rules → focused reference documents

Historical GitLab/KrakenD/DefectDojo/demo procedures removed from this README
remain available through Git history if needed; they are not current operational
sources of truth.
