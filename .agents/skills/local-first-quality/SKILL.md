---
name: local-first-quality
description: Route FastAPI exact-HEAD L0–L3 quality checks; remote API-only sessions keep honest NOT_RUN evidence.
---

# Local-first quality — compact router

Load for CI failure, PR continuation, formatter/lint, offline diagnostics or local-first release work. `AGENTS.md` is authoritative. Do not treat GitHub CI or targeted L1 as local L3.

## Execution selection

- **Connected Claude Code workstation:** explicitly `AGENT_EXECUTION_MODE=workstation`; use worktree-specific Python 3.13 / `uv.lock`, local Node/Just, cached tools and normal security checks. Never run `set -euo pipefail` directly in the operator's interactive shell; use a child script.
- **Remote Codex / no checkout or LAN:** default `AGENT_EXECUTION_MODE=offline`; inspect exact GitHub refs, apply minimal offline contracts and produce a Draft PR. **Never** claim that formatting/security/full pytest/LAN checks ran unless executed. No private network, secret or live runtime calls.
- Both modes: never mutate `master`, bypass hooks, share `.venv` across agents, force a locked `QG_LOCKED` gate, suppress scans or report a PASS from another SHA.

## Evidence levels and commands

| Gate | Workstation command | Strongest evidence |
| --- | --- | --- |
| L0 | `just agent-context auto` | Branch, paths, task/skill route |
| L1 | `just ui-quick`, `just docs-links`, or relevant focused pytest | Only the selected contract |
| L2 | `bash scripts/agent-quality-gate.sh --fix` | Changed-tree deterministic convergence |
| L3 | commit, then `bash scripts/agent-publish.sh` | Full local publication proof at exact SHA |

If no worktree/dependencies: `bash scripts/agent-offline-check.sh` is syntax-only L1, never L2/L3. `[skip ci]` only in explicit no-credit Draft mode. Inspect failing job/step and bounded logs rather than entire CI or repeated polls.

## Conditional references

Read the relevant section of [worktree Python, shell safety, CI convergence, exact-HEAD snapshot and recovery](references/local-quality-details.md) when these details matter. No need to load it for routine code edits.
