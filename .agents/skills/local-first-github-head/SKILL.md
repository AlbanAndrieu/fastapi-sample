---
name: local-first-github-head
description: >-
  Validate an exact GitHub PR/branch HEAD locally without relying on git clone
  or GitHub Actions. Prefer a public source archive; when container DNS/egress
  blocks github.com or codeload.github.com, reconstruct the required snapshot
  from the exact GitHub tree/files through the connector, then run targeted
  tests and quality checks inside the local container.
license: Apache-2.0
role: developer
---

# Local-first validation from an exact GitHub HEAD

## Goal

Run real tests against the exact remote HEAD while consuming no GitHub Actions
credits and without assuming that `git clone`, DNS or direct GitHub egress work.

The validation source must always be pinned to the immutable commit SHA, never
to a moving branch name after the HEAD has been resolved.

## Workflow

1. Resolve the PR/branch HEAD SHA through GitHub and record it.
2. Read the check-runs/statuses for that SHA before making another change.
3. Materialize that exact SHA locally:
   - preferred: download the public GitHub source archive for the SHA through
     the available download channel and extract it into a fresh directory;
   - fallback when the container cannot resolve/reach GitHub: use the GitHub
     connector to read the exact tree/files needed by the targeted test scope
     and materialize those files into a fresh container directory.
4. Verify the materialized files come from the recorded SHA. Never mix files
   fetched from a branch after the SHA was resolved.
5. Run the narrowest meaningful tests first, then expand toward the repository
   quality gate as local tooling/dependencies permit.
6. If a formatter or deterministic fixer modifies files, apply only that
   deterministic patch, publish with `[skip ci]` when CI credits must be
   preserved, resolve the new SHA, and repeat the loop.
7. Before the next roadmap improvement, re-read the checks for the current HEAD.

## Archive-first materialization

Use an immutable archive URL equivalent to:

```text
https://github.com/<owner>/<repo>/archive/<sha>.tar.gz
https://codeload.github.com/<owner>/<repo>/tar.gz/<sha>
```

Download through the environment's approved download channel rather than
assuming shell DNS works. Extract into a new SHA-named directory; never reuse a
working directory containing files from an older HEAD.

If the download channel itself cannot access GitHub, do not fall back to
`git clone`: the same DNS/egress failure will normally recur.

## Connector snapshot fallback

When archive retrieval is unavailable:

- fetch the recursive Git tree for the exact commit/tree SHA;
- fetch only the production files, tests and configuration required by the
  current targeted validation;
- preserve repository-relative paths in the container;
- create only package marker files that exist in the repository or are strictly
  necessary for an isolated Python import test; document any such synthetic
  marker;
- expand the snapshot if an import/test exposes another required file.

This fallback is a targeted validation snapshot, not proof that a full
repository quality gate passed.

## Validation claims

Be precise:

- `pytest ...: PASS` means those exact tests ran against the pinned snapshot;
- `py_compile: PASS` means syntax/import compilation passed for the named
  files;
- do not claim the full quality gate is green unless the canonical repository
  gate itself ran successfully against the same SHA;
- distinguish missing local tooling/dependencies from test failures.

Always report the SHA, commands/tests executed, pass/fail counts and any scope
limitations.

## Proven pattern in fastapi-sample

For the Prometheus/Gatus/pfSense observability refactor, the connector-snapshot
fallback materialized the exact PR HEAD and executed:

```bash
PYTHONPATH=. pytest -q \
  tests/unit/test_platform_metrics.py \
  tests/unit/test_topology_telemetry.py \
  tests/unit/test_collect_pfsense_probe_baseline.py
```

Result on SHA `8564353f91b2fcaca3b5577b88dcfdeaf0e7903e`:

```text
16 passed
```

This validates the fallback itself and makes it the standard local-first escape
hatch when direct GitHub DNS/egress is unavailable.
