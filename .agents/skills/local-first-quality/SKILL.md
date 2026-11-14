---
name: local-first-quality
description: >-
  Route Claude workstation and isolated Codex to bounded local validation;
  protect exact-HEAD publication gates and avoid unnecessary CI/token usage.
---
# Local-first validation

**Authority:** [AGENTS.md](../../../AGENTS.md) controls branches, secrets, CI and publication. This skill is loaded only for a quality or incident task; the old detailed narrative is [archived](../../../docs/archive/2026-11-14-local-first-quality-before-profiles.md).

## Choose executable evidence, not assumed capabilities

| Proof | One command | Result scope |
| --- | --- | --- |
| L0 | `just agent-context auto` | HEAD, changed paths, recommended skill; no tests |
| L1 UI | `just ui-quick` | JS contracts only (Node installed) |
| L1 offline | `just offline-l1` | Python AST, bash, JSON, JS syntax if Node, workflow policy |
| L1 workstation probes | `just agent-diagnostics workstation runtime` | Read-only runtime evidence, **only when requested** |
| L2 | `bash scripts/agent-quality-gate.sh --fix` | Convergent local format, lint, security, tests by scope |
| L3 | `bash scripts/agent-publish.sh` | Clean exact-HEAD publication gate; requires a real checkout |

`just agent-context truenas isolated` never probes LAN. In an isolated Codex container, prefer pure tests, fixtures, versioned files and exact-SHA GitHub review. Declare runtime, Docker, browser and full gates **NOT_RUN** when unavailable. A `403` is DENIED, not a LAN outage. No invented PASS.

On a real Claude workstation, use `FASTAPI_AGENT_PROFILE=workstation` or `just agent-context auto workstation`, then opt into the *one* diagnostic needed: `just agent-diagnostics workstation dns|metrics|runtime`. `auto` uses the explicit local signal `CLAUDECODE=1` only outside CI/Codex. The profile itself does **not** verify the LAN. Run a single check, inspect summarized results, expand only on failure.

## Worktree and execution

- Python 3.13 + locked `uv`/`uv.lock`. Each worktree owns `.venv`; cache sharing is allowed, installation sharing is not. Use `scripts/agent-worktree-python.sh --check` before a deliberate `--sync`.
- Never source a script with `set -euo pipefail` into the user's interactive shell. Execute as a child process (`bash scripts/...`). Never `source .envrc` or print secrets for a diagnostic.
- L1 first, then L2, then L3 on a clean commit. `QG_LOCKED` (75) means another agent validates this worktree; never delete its lock. Do not disable hooks or scanners.
- For GitHub/API-only mode, resolve immutable HEAD and read the smallest files/tests once. If no checkout can be materialized, state `L2/L3 NOT_RUN`; CI may supply separate evidence. Do not repeatedly poll or rerun runners.
- Keep PR Draft while iterating. `[skip ci]` is allowed only when the user explicitly requests no GitHub Actions credits, never for ordinary Ready PRs. Hosted security requirements remain mandatory before merge.

## Reports and communication

Report `PASS/FAIL/INCOMPLETE/NOT_RUN`, exact SHA, commands, observer vantage and **next acceptance proof**. CI green ≠ deployed runtime accepted. Use concise ASD-STE100-inspired sentences: one action per procedure step and one term per concept.

See [execution-profile runbook](../../../docs/agent-execution-profiles.md), [FastAPI roadmap](../../../docs/engineering-roadmap.md), and [canonical script index](../../../scripts/README.md).
