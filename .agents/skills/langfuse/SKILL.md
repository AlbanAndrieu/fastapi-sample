---
name: langfuse
description: Use for Langfuse instrumentation, traces, prompts, datasets, scores, SDK upgrades, or Langfuse-specific debugging.
license: MIT
compatibility: Cursor, OpenCode, Codex, Copilot, Claude Code
metadata:
  scope: observability
  load: on-demand
---

# Langfuse

Use this skill only for Langfuse-specific work.

## Workflow

1. Inspect the repository integration before changing anything.
2. Verify current Langfuse SDK/API documentation when behavior or signatures may have changed.
3. Keep secrets out of logs and code; use environment-backed settings.
4. Prefer explicit instrumentation and lazy/runtime initialization over module-import side effects.
5. Preserve privacy defaults: do not capture prompts, responses, tool arguments, or user content unless the task explicitly requires it.
6. Validate with focused tests plus the repository quality gate.

## References

Read only the reference needed for the task:

- `references/instrumentation.md` — instrumentation patterns.
- `references/error-analysis.md` — tracing/debugging failures.
- `references/sdk-upgrade.md` — SDK migrations.
- `references/prompt-migration.md` — prompt migration.
- `references/ci-cd.md` — CI/CD integration.
- `references/cli.md` — CLI/API access.

Do not preload the whole `references/` directory into context.
