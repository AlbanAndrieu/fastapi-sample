---
name: sentry-workflow
description: Use for Sentry SDK configuration, upgrades, runtime error investigation, or Sentry/Seer findings on pull requests.
license: Apache-2.0
compatibility: Cursor, OpenCode, Codex, Copilot, Claude Code
metadata:
  scope: observability
  load: on-demand
---

# Sentry workflow

Use this skill only for Sentry-related work.

## Workflow

1. Identify whether the task is runtime debugging, SDK configuration, SDK upgrade, or PR finding remediation.
2. Inspect the repository's current Sentry initialization and dependency version.
3. Verify current Sentry documentation for version-sensitive APIs.
4. Keep Sentry optional at runtime: the application must not fail to start solely because Sentry configuration is absent unless explicitly required.
5. Never log DSNs, auth tokens, request secrets, or sensitive payloads.
6. Prefer focused regression tests for the failure being fixed, then run `bash scripts/quality-gate.sh`.

Avoid loading unrelated Sentry workflow material or inventing missing sub-skills. Work directly from the repository and current documentation when needed.
