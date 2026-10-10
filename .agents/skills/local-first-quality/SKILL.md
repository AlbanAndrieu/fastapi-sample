---
name: local-first-quality
description: Validate changed code offline first, converge deterministic gates, and require exact-HEAD publication evidence before merge.
---

# Local-first quality — fastapi-sample

Adapted from `AlbanAndrieu/nabla-compose` PR #251, source commit
`6440eaeda0b32b6d901abd92dd700b91d143b23c`,
`.agents/skills/local-first-quality/SKILL.md`.
Use for CI failures, PR continuation, DNS outages, formatter/linter fixes,
agent-output reduction and local-first quality gates.

**Repository authority:** `AGENTS.md`, `docs/engineering-roadmap.md`,
`scripts/agent-quality-gate.sh` and `scripts/agent-publish.sh`.
Do not assume commands from `nabla-compose` exist here.

## Evidence levels

| Level | Evidence | Permitted claim |
| --- | --- | --- |
| L0 | Exact-file/static inspection | Inspected, not tested |
| L1 | Executed targeted test/config/syntax on real file bytes | Targeted proof only |
| L2 | Deterministic changed-file fixes and relevant hooks converged | Local convergence only |
| L3 | Canonical publication gate completed on exact clean HEAD, base and toolchain | Complete local gate green |

Never describe L0/L1/L2 as full CI or L3. Missing tools, CI statuses or
dependencies mean **NOT RUN**, not PASS.

## Before editing

1. Read Git status, branch, SHA, comparison base and current PR/check state.
   Fix known failing CI before implementing another roadmap item.
2. Read only the relevant source, nearby tests and roadmap. Load this skill
   on demand, not all skills into agent context.
3. Check the Git-only safety constraints before costly dependency work:
   clean intended branch, valid comparison base, no destructive diff or
   executable-bit regression. The canonical agent gate enforces these.
4. Make a bounded logical change. Never rewrite `master`, automatically
   merge, rerun GitHub Actions merely for formatting, or bypass a hook.

## Fast deterministic loop

```bash
# Within a locally available checkout with installed dependencies:
bash -n scripts/agent-quality-gate.sh
just test                     # or focused: bash scripts/run-pytest-compact.sh tests/unit/...
just fix                      # deterministic pre-commit convergence + validation
git diff --check
git status --short
git diff --stat
# Commit the reviewed logical batch; use [skip ci] when remote credits are constrained.
just publish-check            # canonical scripts/agent-publish.sh, clean committed HEAD
```

`just fix` runs `scripts/agent-quality-gate.sh --fix`, **not** the
`nabla-compose` `--loop` mode. `just publish-check` is the L3
equivalent of `nabla-compose` `agent-pre-push`. It includes scope-aware
build checks. If any formatter changes files, review and commit only those
changes, then rerun on the new HEAD. Do not claim L3 until it passes.

Never drop SAST, BetterLeaks, pre-commit, pytest, Playwright or ZAP from
their required scopes to get green. Browser/DAST acceptance may require a
separate environment and must be labelled NOT RUN if unavailable.

## Disconnected / DNS-blocked environment

- Pin the PR HEAD from GitHub connector metadata; check existing workflows
  and statuses on **that SHA**, not on a previous commit.
- Prefer a pre-existing local Git cache containing the target SHA and base:
  `bash scripts/agent-source-snapshot.sh SOURCE_GIT_DIR HEAD_SHA DEST`.
  The resulting local Git checkout retains metadata needed for the
  canonical gate. Prove `git rev-parse HEAD` matches the expected SHA
  and the comparison base exists.
- When no cached commit exists, inspect existing exact-SHA workflow
  artifacts (do **not** create a workflow merely for a snapshot). Source-only
  archives lack `.git`; they do not prove ancestry or L3.
- Otherwise use GitHub connector `fetch_file` and file SHA leases to
  reconstruct the exact affected files and fixtures locally. Label this
  **L1 targeted reproduction**, not full checkout or L3.
- For Bash execute `bash -n` plus matching available ShellCheck/shfmt,
  and execute affected behavior in temporary fixtures. For Python use
  `python -m py_compile` and the smallest pytest module. If a failure is
  Git-dependent, use an ephemeral Git repository and test both the failure
  and normal behavior. Never run mutating homelab commands for a smoke test.
- Do not repeatedly retry known blocked GitHub/PyPI hosts, or use
  `SKIP`, `--no-verify` or empty test selectors to claim success.
- Full logs stay on disk; agent output contains first actionable failure,
  bounded excerpt, source file and exact SHA.

Operational runbook: [local-first-source-snapshot.md](../../../docs/local-first-source-snapshot.md).

## Remote CI and publication

Use remote status to find the first failing workflow, job and step; expand
logs only if necessary. A missing status is not a passing check.
Preserve required security scanners and generated contracts.

After publication record a compact matrix: HEAD, base SHA, toolchain,
executed commands, `PASS`/`FAIL`/`NOT RUN`, and any missing external
acceptance evidence. Keep draft if L3 is not proven. Never merge automatically.

## Dagger and source generation

Dagger is an optional P1 parity experiment, not a second quality authority.
Use the existing `just` and `mise` entrypoints; do not copy
`nabla-compose`-only `dagger-*` recipes into this repository without
implementing and pinning them. Require locked images/modules, no secrets in
cacheable layers, native-tool parity, then local versus CI results at one SHA.
Use Context7 for current library documentation when available, but the
repository contracts are authoritative.
