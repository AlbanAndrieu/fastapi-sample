---
name: homelab-runtime-status
description: Validate runtime vs declared service status, application health and exposure when runtime evidence is relevant.
---

# Homelab runtime status — compact router

Read `AGENTS.md` and classify the task before probing:

- **Remote Codex/offline:** inspect code, DTO definitions, tests, cached evidence and GitHub PRs only; do **not** call LAN endpoints. Mark runtime `NOT_RUN`, never `DOWN` or `HEALTHY` without fresh evidence.
- **Connected workstation Claude Code:** opt in `AGENT_EXECUTION_MODE=workstation`, use `bash scripts/agent-diagnostics.sh --runtime` for bounded evidence or `--dns-only` for DNS. Scope further with existing runbooks. Do not wake an idle Cloud instance or poll repeatedly.
- **Independent axes:** `/api/homelab/status` = binding; `/api/homelab/health` = functional evidence; `/api/homelab/runtime` = observed container/TrueNAS; `/sickz` = exposure, **not** normal availability. `DENIED` and `NOT_RUN` do not prove a service failure.
- **Completion gate:** log timestamp, observer vantage, target, deployed SHA/`catalogRevision`, source, and unresolved tests in `docs/engineering-roadmap.md`; do not claim cutover from a green dashboard alone.

Load only the needed sections from [endpoint map, cutover/acceptance details](references/runtime-inspection.md). The extended procedure is not startup context.
