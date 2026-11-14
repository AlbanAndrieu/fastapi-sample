# Agent execution profiles — workstation and isolated Codex

> Task-specific reference; not an always-loaded policy. `AGENTS.md` is authoritative. Profiles affect **which tests can be run**, not authorization, network access or the meaning of evidence.

## Fast start

| Agent/environment | Context | Safe diagnostic |
| --- | --- | --- |
| Claude Code on workstation with LAN | `just agent-context auto workstation` | `just agent-diagnostics workstation runtime` |
| Claude Code DNS only | `just agent-context truenas workstation` | `just agent-diagnostics workstation dns` |
| Claude Code Prometheus LAN only | `just agent-context metrics workstation` | `just agent-diagnostics workstation metrics` |
| Codex container without LAN/checkout | `just agent-context auto isolated` | `just agent-diagnostics isolated runtime` (L1 if a checkout exists; runtime NOT_RUN) |
| Any agent, no probes desired | `just agent-diagnostics auto runtime --plan` is **not** a Just recipe option; use `bash scripts/agent-diagnostics.sh --profile auto --scope runtime --plan` | Plan only, no network |

CLI router: `python3 scripts/agent-task-context.py --task auto --profile auto --json`. It reads Git status and names only (never secrets or network). `auto` defaults to `isolated`; `FASTAPI_AGENT_PROFILE=workstation` or `CLAUDECODE=1` may select workstation outside CI/Codex. Any `CI` or `CODEX_HOME`/`CODEX_THREAD_ID` forces isolated. Explicit workstation choice is a **declaration**, not a successful connectivity test.

## Diagnostic scopes

| Scope | Workstation (opt-in; read only) | Isolated result |
| --- | --- | --- |
| `runtime` | `truenas-runtime-evidence.sh --vantage workstation --detail` (bounded cached board, local Docker metadata and readiness) | Offline L1; TrueNAS NOT_RUN |
| `dns` | `truenas-runtime-evidence.sh --vantage workstation --dns-only` (resolver comparison) | Offline L1; DNS NOT_RUN |
| `metrics` | `verify-prometheus-cloud-projection.py --check --scope lan` (Prometheus LAN) | Offline L1; scrape NOT_RUN |
| `metrics-both` | Same checker with `--scope both` (LAN + Cloud; may require DIAGNOSTICS_ACCESS_KEY) | Offline L1; Cloud NOT_RUN |
| `offline` | `agent-offline-check.sh` (syntax and changed-file policy) | Same |

`bash scripts/agent-diagnostics.sh --profile workstation --scope runtime --plan` prints the command instead of executing it. **Do not start any live diagnostic automatically from `CLAUDE.md`, `AGENTS.md` or agent-context**. Invoke a bounded scope only when the task needs live evidence.

## Resource and token policy

1. Read current HEAD, changed files, nearest source/test and one matching skill. Limit output (`--json` when scripting); avoid whole CI logs, full catalog data and unrelated repositories.
2. Use existing workstation Python 3.13 `.venv`, Node, Git, Docker metadata, DNS and Gatus/Prometheus on demand. Never auto-install, inspect secret environments or perform mutations.
3. In isolated Codex, run Python AST, JSON, Bash/Node syntax, unit tests and GitHub exact-SHA analysis that are **actually accessible**. If no checkout or dependency is available, label the missing L1–L3 proof NOT_RUN; do not attempt private network routes.
4. Keep observed (runtime/health), declared (Backstage) and exposure (sickz) signals separate. A failed request can be DENIED, NOT_RUN or stale rather than DOWN.
5. Report only facts: SHA, origin, exact command, PASS/FAIL/NOT_RUN, and next acceptance proof. Do not print secrets, private endpoint bodies or raw infrastructure JSON.

## Skill and documentation ownership

- `CLAUDE.md` includes `AGENTS.md`; `.claude/skills` is a symlink to `.agents/skills`. Never copy an identical rule into both.
- Full previous instructions are archived for historical reference under `docs/archive/2026-11-14-*before-profiles.md`; they are **not** a current second policy.
- FastAPI-specific follow-ups: [engineering roadmap](engineering-roadmap.md). Infrastructure operations: the linked `nabla-compose` runbooks. Diagnostics: [scripts index](../scripts/README.md).
