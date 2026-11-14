# fastapi-sample — Agent Guide

`AGENTS.md` is the single cross-agent policy; Claude loads it through `CLAUDE.md` (`@AGENTS.md`). Do not copy it into individual skills or agent adapters. Load only the task-specific skill and the nearest source/tests. Extended operations: [agent playbook](docs/agent-execution-playbook.md).

## Mission, safety and ownership

- Own FastAPI API, observer, DTOs, UI, runtime cost, application tests. `nabla-compose` owns TrueNAS/pfSense/Cloudflare/Vaultwarden, monitoring targets, Backstage source; Site Alban owns Next.js presentation.
- Never mutate `master`, disable a quality/security gate, reveal `.env`/tokens, expose a LAN service, change YubiKey material or merge a PR without approval. Reversible homelab downtime is permitted; irreversible data loss/exposure is not.
- Prove **CODED / TESTED / DEPLOYED / ACCEPTED** separately. `NOT_RUN`, `DENIED` and stale telemetry are not verified `DOWN`. Record SHA, vantage, source and next required acceptance in `docs/engineering-roadmap.md`.

## Execution modes (based on actual access, not agent branding)

- **Connected Claude Code workstation:** explicitly opt in using `AGENT_EXECUTION_MODE=workstation` **only when** the checkout, dependencies and LAN routes are really available. Use workstation CPU/uv/Node/Just, cached deps, local tests, Docker metadata and bounded TrueNAS probes as needed. Runtime work must be read-only unless separately authorized.
- **Remote Codex / GitHub connector / no LAN:** default `AGENT_EXECUTION_MODE=offline`. Do the code, review, tests possible in the environment, documentation, GitHub PRs and static validations. Never attempt private IP/SSH/Docker/TrueNAS, secrets or login based on a hostname from docs. Runtime is `NOT_RUN`; provide the workstation acceptance command.
- Start with `python3 scripts/agent-task-context.py --task auto`; it is path-only and **never probes** the LAN. To execute a diagnostic, use `bash scripts/agent-diagnostics.sh --help`. Only an explicitly selected workstation mode enables `--runtime`; use `--dns-only` to isolate DNS.
- Separate Git worktrees/virtual environments for concurrent agents; a `QG_LOCKED` status is not permission to delete a quality gate lock.

## Mandatory execution protocol

1. Resolve task, selected PR state, branch and exact remote HEAD. Inspect `git status --short`, changed paths, nearest source and tests; read only the relevant roadmap heading. Do not preload full roadmaps, logs, snapshots, entire skill trees or connector schemas.
2. Load matching skills on demand (see below). Perform the smallest logical edit and one focused L1 check. Use `just agent-context auto` and its recommended `firstCheck` when available.
3. With workstation toolchain, converge **L2** via `bash scripts/agent-quality-gate.sh --fix`, review diffs, commit, then prove **L3** via `bash scripts/agent-publish.sh` on the exact HEAD. `just ui-quick` and `just docs-links` are L1, not publication proof.
4. With no executable checkout, run only possible offline checks, batch one Git commit with an expected SHA and keep a **Draft PR**. Declare L2/L3/CI/runtime **NOT_RUN** instead of treating an API write as a gate bypass.
5. Inspect failing CI job/step and bounded log excerpts first. No redundant polling; preserve SAST/SCA/secret scanning. In explicit **no-GitHub-Actions/no-credit mode**, keep Draft and use the established `[skip ci]` exception only as directed; no merge until required reviews.
6. Before reporting completion, update `docs/engineering-roadmap.md` with any unresolved issue, owner and acceptance command. Report changes, tests actually run and residual risks.

### Skill routing

| Trigger | Load only when needed |
| --- | --- |
| CI, local quality, PR convergence | `local-first-quality` |
| API/Pydantic/routes | `fastapi` |
| Cloud CPU/memory/deploy | `fastapi-cloud` |
| Observed service status and migrations | `homelab-runtime-status` |
| Backstage service graph / evidence semantics | `homelab-service-contract` |
| pytest contracts | `pytest-contract-testing` |
| pfSense | `pfsense-api-debugging` |
| Redis | `redis-async-lifecycle` |
| Sentry | `sentry-workflow` |
| PostgreSQL/Supabase | `supabase-postgres-best-practices` or `supabase` |

Skills under `.agents/skills/<name>/SKILL.md` augment but never override safety or publication policy. `.claude/skills` may be a symlink; do not duplicate skills.

## Useful references

- [Quality/agent workflows, migrations, code size, toolchain, GitHub limits](docs/agent-execution-playbook.md) — conditional, not session startup.
- [Current FastAPI engineering roadmap](docs/engineering-roadmap.md), [documentation map](docs/README.md).
- `just --list`, `just offline-l1`, `just ui-quick`, `just docs-links`, `just quality`, `just publish-check`.
