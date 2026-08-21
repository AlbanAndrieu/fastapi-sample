# Claude Code Instructions

Follow `AGENTS.md` as the repository-wide engineering policy.

## Claude-specific workflow

Before implementing a non-trivial change:

1. inspect the relevant code and tests;
2. identify the smallest safe change;
3. verify uncertain third-party behavior against current official documentation;
4. implement the change;
5. run focused tests first;
6. run broader repository quality checks when appropriate.

Prefer repository exploration over loading large amounts of documentation into context.

Use subagents for independent exploration, review, or investigation when this keeps unrelated information out of the main context.

Do not create additional abstractions, documentation, configuration, rules, or skills unless they materially help the requested task.

For repository commands, prefer `uv` and repository-managed scripts.

Never expose secrets or modify secret environment files unless explicitly requested.

When modifying a large Python module, apply the maintainability thresholds and refactoring rules from `AGENTS.md`, including the **400/700-line file thresholds**.

Before pushing, follow the quality and Git requirements from `AGENTS.md`.

When uncertain, inspect the repository rather than guessing.
