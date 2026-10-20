---
name: local-first-quality
description: >-
  Fast, exact-HEAD Python/CI security validation without wasting GitHub Actions
  credits; never weaken quality gates.
---
# Local-first quality (canonical task-specific skill)

`AGENTS.md` owns repository safety; the only publication authority is
`scripts/agent-publish.sh`. Load this skill **on demand** for CI,
agent efficiency, missing DNS or GitHub snapshot validation.

## Evidence levels
| L0 | Inspection only | Not tested |
| L1 | Focused test/syntax on exact files | Narrow check only |
| L2 | Changed-file hooks, formatting and security converge | Local proof |
| L3 | Clean exact HEAD, `scripts/agent-publish.sh` succeeded | Full local gate |

Never describe L0–L2 as full CI/L3. Missing dependencies/tools,
remote runtime or DAST = **NOT_RUN**.

## Minimal loop
1. Resolve current branch, PR HEAD and base once. Inspect changed files,
    immediate tests, failing CI job/step only; avoid giant GitHub diffs,
    full roadmap and unrelated skills.
2. Keep changes in one logical patch; use `uv` / `just`. For a real
    checkout run targeted tests → `bash scripts/agent-quality-gate.sh --fix`
    → review diff → clean commit → `bash scripts/agent-publish.sh`.
3. When DNS/clone is unavailable, use an immutable cached Git snapshot
    with `scripts/agent-source-snapshot.sh`; otherwise materialize exact
    GitHub file bytes needed for focused tests. Don't invent a green L3.
4. In no-credit mode use `[skip ci]`, stay Draft and avoid repeated
    DAST/Sonar/MegaLinter runs. Never disable Betterleaks/Trivy Critical,
    pre-commit, pytest, CodeQL or any required security scan.
5. Publish with expected-SHA concurrency guard, one batch. On conflict,
    reread only concurrently changed files. Recheck the published SHA once.

## GitHub issue hygiene (one source of truth)
`.github/workflows/master-red-remediation.yml` and
`scripts/ci/master_red_issue.py` update only the bot-owned status comment
in [#355](https://github.com/AlbanAndrieu/fastapi-sample/issues/355).
Do **not** create issues/PRs per SHA, or mutate title/body/labels.
Before first enrollment, compare the reviewed `updated_at`, historical
manual issue events **and human comments**; afterwards verify fingerprint,
manual events and status-comment integrity.
Close only after two consecutive green master-red workflow numbers;
human edits prohibit auto-reopen. Test with
`python3 -m unittest tests.unit.test_master_red_issue -v`.

## Speed / token budget
- Begin with `PR HEAD + changed paths + one failing job/step`; batch independent reads.
- Avoid repeated CI polling, full 20k-line logs, GitHub-wide issue searches,
  large PR diffs and full skills catalog loads when an exact path is known.
- One atomic patch, then only focused offline tests. Fetch a new HEAD once,
  and inspect only failed checks; do not create placeholder remediation PRs.
- Preserve actual results: `PASS` / `FAIL` / `NOT_RUN` / `INCOMPLETE`.
  Tool/network access and CI outcomes must never be inferred as successes.

## Documentation
Read the current `docs/engineering-roadmap.md` topic only. Long-tail
unchecked work in `docs/engineering-backlog.md` needs re-triage;
completed narratives are Git history. Preserve unique failure signatures
and recovery commands in `docs/incidents.md` or `nabla-compose` runbooks.
Report exact SHA, executed checks and residual `NOT_RUN` work.
