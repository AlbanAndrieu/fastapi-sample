---
description: Continue the selected FastAPI PR with a bounded local-first edit loop
agent: build
---

Resume the **current selected PR**, not a neighboring issue or roadmap item.

1. Read `AGENTS.md` and verify the selected PR is open, Draft, and points
   to the expected remote HEAD. Never edit `master`.
2. Run `just agent-context ui` for `/api` UI work, or select a
   task-specific `agent-context` mode. This command is offline and does
   not expose environment values.
3. Read only the indicated skill, changed paths, and closest tests.
   When investigating the rich dashboard, compare `?ui_safe=1` with
   `?ui_full=1`; the safe page working does not prove the full page works.
4. Pick one finishable regression within the PR scope. Name the exact
   source/test files and one falsifiable acceptance check.
5. Reproduce the failure locally if a checkout is available. Run
   `just ui-quick` for UI changes; keep Node tests independent of
   `npm install` or any browser.
6. Apply one small reviewed edit batch. Avoid repeated broad GitHub
   searches, large logs, unnecessary PRs, and unrelated refactors.
7. Run `bash scripts/agent-quality-gate.sh --fix` in the worktree
   when dependencies are available. Review the formatter diff.
8. On a **clean committed HEAD**, run `bash scripts/agent-publish.sh`
   before publication. Do not replace it with Compose's `agent-pre-push`.
9. Keep the PR Draft with `[skip ci]` only while the owner requests
   zero-credit local-first. Do not merge, redeploy or dispatch CI.
10. Report exact SHA, tests that actually ran, remaining `NOT_RUN`
    checks, and the next concrete blocker. Separate Cloud, TrueNAS,
    and workstation evidence.

Do not read or print live `.env*` values. Do not treat HTTP 401/403,
`readOnlyDiagnostics=true`, or `gatus_up=1` as overall service health.
