# FastAPI Sample — agent instructions

**Authority:** this file is the only always-loaded policy. Claude Code reads it via `CLAUDE.md`; Codex/OpenCode read it directly. Load only one relevant `.agents/skills/<name>/SKILL.md` on demand. `.claude/skills` is a symlink, not a second skill set.

## Mandatory execution protocol

1. Resolve the **current HEAD/base**, branch, worktree status and changed paths once. **Une worktree Git par agent** : never edit the same checkout concurrently. Protect `master`: work on a branch/worktree; never push to `master`.
2. Route the task with `just agent-context auto` (or `python3 scripts/agent-task-context.py --task auto --json`). Read only its recommended skill, the relevant roadmap section, source and nearest tests. Do not preload entire skills, logs, history or catalog JSON.
3. Change the smallest cohesive set of files. Preserve existing API/security contracts, type hints, and backward compatibility. No network/DB/telemetry work during Python import. Python files >400 lines need review and >700 lines need splitting for significant changes.
4. Run the **first targeted check** from agent-context. Where a checkout and dependencies exist, converge with `bash scripts/agent-quality-gate.sh --fix`, review diff, commit to a non-default branch, then `bash scripts/agent-publish.sh` on clean exact HEAD. These are the only canonical L2/L3 gates. For all pytest failures: `QUALITY_PYTEST_MAXFAIL=0 QUALITY_LOG_TAIL=80 bash scripts/agent-quality-gate.sh --fix`. `QG_LOCKED` (75) means another validator owns the worktree; do not delete the lock.
5. Publish only via PR, with expected-SHA safety on GitHub API edits. An API-only agent lacking an executable checkout must report local gates **NOT_RUN**, use immutable-SHA focused tests if possible, and inspect CI rather than asserting local success. Never bypass hooks or weaken SAST/SCA/DAST, quality, scan, auth or branch protections.
6. Do not merge or deploy without explicit authorization. Standard PR commits have **no `[skip ci]`**. In an expressly requested **no-GitHub-Actions/no-credit mode**, keep PR Draft, `[skip ci]` is exceptional, mark hosted checks NOT_RUN and restore required checks before merge. No silent CI rerun.

## Execution profiles — workstation vs isolated

- `just agent-context auto workstation`: explicitly select a local workstation with appropriate tools/network. `FASTAPI_AGENT_PROFILE=workstation` can select it for Claude Code. `CLAUDECODE=1` may suggest workstation in `auto` only when neither CI nor Codex is detected. **A profile is not proof of LAN access.**
- `just agent-context auto isolated`: Codex/container without the operator LAN or Docker/TrueNAS credentials. `auto` defaults to isolated unless a deliberate local signal exists; CI and Codex detection override Claude detection. Never probe RFC1918 addresses or invoke TrueNAS, pfSense, Docker, Vaultwarden, or authenticated endpoints as if available.
- Use `just agent-diagnostics workstation runtime|dns|metrics` only for a **read-only, explicitly requested** workstation diagnosis. Use `just agent-diagnostics isolated runtime` or `just offline-l1` in isolated mode: syntax/tests, fixtures, schema, GitHub exact-SHA review; report live evidence NOT_RUN. No LAN fan-out on startup.
- Execute Python with the worktree's locked `uv` / Python 3.13 environment. `.venv` is private to each worktree; the uv download cache may be shared. Do not install globally, source `.envrc` or print env secrets.

## Evidence, security and ownership

- Use **L0** inspection, **L1** targeted test, **L2** changed-file local gate, **L3** clean exact-HEAD publish gate. Report PASS/FAIL/INCOMPLETE/NOT_RUN with SHA and environment; CI/PR green is **not** runtime ACCEPTED.
- `DENIED`, `NOT_RUN`, `NO_SAMPLE` and `STALE` are **not** `DOWN`; declarations, observations, health and internet exposure are distinct. A cloud 403 is not a TrueNAS outage. Never infer accessibility from DNS, dashboard green or catalog metadata.
- No plaintext secrets, tokens, passwords, private IPs or internal URLs in PUBLIC DTOs, logs or commits. Do not mutate `.env`, `.env.local`, `.env.secrets`, certificate/YubiKey state, firewall, backup, DB or Cloudflare policies unless explicitly asked and authorized.
- `nabla-compose` owns TrueNAS, pfSense, Cloudflare, Gatus/Prometheus targets, infrastructure mutations, and the H portfolio. FastAPI owns API/health semantics, consumers, caches, diagnostics and tests. `nabla-site-alban` owns Next.js presentation. This repository's `compose.yml` is the TrueNAS application deployment definition; `docker-compose.yaml` is local development.
- The canonical FastAPI backlog is `docs/engineering-roadmap.md` (current order H05/F03+F09 then H17/F11); `docs/engineering-backlog.md` is historical, and `docs/incidents.md` holds dated incidents. Do not reopen archived E aliases or duplicate runbooks. The unique master-red tracker is issue #355, governed by `scripts/ci/master_red_issue.py` and two distinct successful master runs.

### Skill routing

| Trigger | Load one focused skill |
| --- | --- |
| CI, local-first, offline snapshot | `local-first-quality` |
| GitHub exact SHA without checkout | `local-first-github-head` |
| FastAPI routes/Pydantic | `fastapi` |
| Cloud runtime | `fastapi-cloud` |
| TrueNAS/LAN checks (only on workstation) | `homelab-runtime-status` |
| Catalog identity, topology, declared vs observed | `homelab-service-contract` |
| Pytest | `pytest-contract-testing` |
| pfSense | `pfsense-api-debugging` |
| Redis | `redis-async-lifecycle` |
| Sentry | `sentry-workflow` |
| Supabase/Postgres | `supabase-postgres-best-practices` |

## Completion gate

An agent **must not declare work complete** while any **known residual**, deferred validation, cross-repository follow-up, or security risk is unrecorded in `docs/engineering-roadmap.md`. Record its owner, state and **next acceptance proof**, then report changed files, exact executed checks, and NOT_RUN items. No HTTP 200, Docker RUNNING or green dashboard alone establishes acceptance.

## Further reference (read only when needed)

- [Execution profiles and diagnostics](docs/agent-execution-profiles.md) — workstation, Codex and bounded scripts.
- [Documentation index](docs/README.md), [canonical scripts](scripts/README.md) and [runbooks](docs/runbooks/).
- [Pre-optimization agent reference](docs/archive/2026-11-14-agent-guide-before-profiles.md) — historical detailed guidance (not an overriding policy).
- User-facing procedures: clear ASD-STE100-inspired sentences; one action per step; no unverified claims.
