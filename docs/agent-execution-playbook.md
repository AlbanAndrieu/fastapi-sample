# FastAPI agent playbook — conditional reference

Read `AGENTS.md` first. This document is on-demand; the assistant must not load it for every startup or repeat it in `CLAUDE.md`.

## Workstation and disconnected modes

| Operation | Workstation (explicit `AGENT_EXECUTION_MODE=workstation`) | Remote Codex / API-only (default `offline`) |
| --- | --- | --- |
| Source context | Targeted git files, local worktree, exact SHA | Narrow GitHub refs/files or available checkout |
| CPU-intensive checks | Existing uv/Node/mise cached dependencies, local formatter and tests | Only feasible offline syntax/unit checks; no invented gate result |
| TrueNAS diagnosis | `scripts/agent-diagnostics.sh --runtime` (bounded quick) | `--runtime` blocked with `NOT_RUN` |
| DNS-only triage | `scripts/agent-diagnostics.sh --dns-only` | Blocked; no LAN/DNS inference |
| Publishing | L1 → local `agent-quality-gate.sh --fix` → commit → `agent-publish.sh` | Draft PR, expected-SHA write, disclose L2/L3 NOT_RUN |

```bash
# Connected Claude Code workstation:
AGENT_EXECUTION_MODE=workstation bash scripts/agent-diagnostics.sh --runtime
AGENT_EXECUTION_MODE=workstation bash scripts/agent-diagnostics.sh --dns-only

# Remote disconnected Codex (never probes the LAN):
AGENT_EXECUTION_MODE=offline bash scripts/agent-diagnostics.sh --static
# --runtime is rejected with NOT_RUN (exit 2).
```

The `--runtime` route delegates to `scripts/truenas-runtime-evidence.sh --quick`, which retains its existing default full-check behavior and adds a bounded short-polling mode. Quick observations cannot replace full, authenticated runtime acceptance.

## Toolchain and quality

- Bootstrap hooks on an authorized local checkout with `mise run hooks`; use `uv` and `just` rather than introducing Poetry. Legacy `Makefile` stays for explicit specialty workflows.
- For source changes run `just ui-quick` or relevant pytest first. Then `bash scripts/agent-quality-gate.sh --fix` (convergent L2); inspect formatter changes; `bash scripts/agent-publish.sh` only on a committed clean HEAD (strict L3).
- If Python code is over 400 lines, review extraction opportunities; over 700 lines normally requires modularization. Avoid unrelated refactoring and import-time API/network initialization.
- Never force-delete a worktree quality lock. If dependencies or network are missing, `just offline-l1` provides syntax-only evidence and is not a security gate.
- For a docs-only change, `just docs-links` checks active local Markdown without loading archived reports. When a change includes source, use its source test path instead of routing it as docs-only.

## Debugging and task ownership

- `nabla-compose` owns source monitoring targets and TrueNAS operations; FastAPI only reads/project statuses and may cache evidence. Do not copy infrastructure runbooks.
- On FastAPI Cloud, distinguish public observer and OWNER, true process/host CPU versus billed resource metrics, and no extra public polling. `F01/F02/F03/F09/F11` are owned by the [roadmap](engineering-roadmap.md).
- For UI incidents, inspect relevant `nabla/api/assets/` and `tests/js/` source first; only fetch screenshot/trace when needed. For private probes, keep Access `403` distinct from transport failures.
- CI workflow/job → failed step → bounded logs/trace. Do not download healthy workflow logs, continuously poll checks, or dispatch remote CI just to find formatting mistakes.
- Master-red issue automation uses `scripts/ci/master_red_issue.py` and issue #355; never overwrite human edits or close without its two distinct successful master proofs.
- GitHub CI minutes and Vercel/FastAPI Cloud runtime costs are different budgets. Hosted green is independent from local L3, and neither proves target runtime.

## Conditional skills

- [Local-first quality](../.agents/skills/local-first-quality/SKILL.md)
- [Runtime endpoints and cutovers](../.agents/skills/homelab-runtime-status/references/runtime-inspection.md)
- [Service catalog DTO contract](../.agents/skills/homelab-service-contract/SKILL.md)
- [Documents/incident index](README.md)
