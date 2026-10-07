---
name: local-first-head-validation
description: >-
  Validate an exact public GitHub HEAD without git clone when DNS/network access
  from the execution container is unavailable. Prefer a downloaded repository
  archive; fall back to a GitHub-connector targeted snapshot, then archive,
  extract and execute tests from the extracted tree.
---
# Local-first exact-HEAD validation

Use this skill when local validation is required but `git clone`, `git fetch`,
or direct DNS from the execution container is unavailable or unreliable.

The goal is to validate the **exact remote HEAD being reviewed**, not a manually
recreated approximation and not the default branch.

## Invariants

- Resolve and record the exact branch HEAD SHA before validation.
- Never claim a test validates the current HEAD after that branch has moved.
- Do not require a `.git` directory for targeted pytest, compile, lint, parser
  or generator checks that only need repository files.
- Run tests from a fresh extracted directory, not from the staging directory
  used to assemble the snapshot.
- Record enough evidence to reproduce the run: HEAD SHA, archive checksum,
  selected files/tests, command and result.
- A targeted pass is not evidence that the repository-wide quality gate passed.

## Strategy A — public HEAD archive

Prefer the public repository archive when the execution environment can obtain
it through its supported download channel.

Resolve the SHA first, then download the immutable archive corresponding to that
SHA rather than a mutable branch name.

Conceptually:

```text
GitHub branch -> exact SHA
        |
        v
public SHA archive
        |
        v
checksum
        |
        v
fresh extraction (no .git)
        |
        v
targeted validation
```

After download:

```bash
sha256sum head.tar.gz
mkdir -p /tmp/head-extracted
tar -xzf head.tar.gz -C /tmp/head-extracted --strip-components=1
test ! -d /tmp/head-extracted/.git
```

Run only tools already available locally. Do not turn a DNS outage into a
package-install attempt that also requires network access.

## Strategy B — DNS-free targeted GitHub snapshot

If the archive channel rejects the URL, or the container itself cannot resolve
GitHub/codeload hosts, use the connected GitHub API as the source of exact file
contents.

1. Resolve the immutable HEAD SHA through GitHub.
2. Determine the smallest transitive file set needed by the intended checks:
   modified modules, imported local modules, tests, and required config.
3. Fetch each file explicitly at that exact SHA.
4. Materialize those files under a clean staging root while preserving paths.
5. Add package marker files only when Python import mechanics require them and
   record that they are harness files, not repository evidence.
6. Archive the staged snapshot locally.
7. Extract that archive into a second clean directory.
8. Execute validation from the extracted directory with `PYTHONPATH` rooted
   there.

Example validation:

```bash
export PYTHONPATH="$PWD"

python -m py_compile \
  nabla/api/prometheus_query.py \
  nabla/api/platform_metrics.py

pytest -q \
  tests/unit/test_platform_metrics.py \
  tests/unit/test_topology_telemetry.py
```

This fallback is appropriate for deterministic targeted checks. It is **not** a
replacement for repository-wide checks whose behavior depends on the full Git
history, ignored files, submodules, generated binary assets, or `.git`
metadata.

## Dependency policy

Before running the snapshot:

```bash
python --version
command -v uv || true
command -v pytest || true
command -v ruff || true
```

Inspect required Python modules with imports before attempting installation.
When dependencies are already present, use them directly.

When a dependency is missing and network/package resolution is unavailable,
report that check as blocked. Do not silently substitute a different tool or
weaken the quality gate.

## Exact-HEAD proof

A successful report should look like:

```text
HEAD: <40-char SHA>
source: public archive | github targeted snapshot fallback
archive_sha256: <sha256>
git_metadata: absent
checks:
  py_compile: PASS
  pytest targeted: 16 passed
repository-wide gate: NOT CLAIMED
```

If the branch changes after the snapshot was created, resolve the new SHA and
repeat the affected validation before publishing code.

## Publication workflow

Before modifying the branch:

1. inspect current checks/statuses;
2. validate the candidate change in the local snapshot when possible;
3. publish with `[skip ci]` when the repository policy intentionally avoids
   consuming GitHub Actions credits;
4. resolve the new HEAD;
5. repeat exact-HEAD targeted validation when the published change affects the
   tested files.

Keep CI and local evidence distinct in PR descriptions.
