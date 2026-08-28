# 1.4.1 release manifest

## Purpose

`1.4.1` is the first patch release after the repository was consolidated back onto the checked-in `1.4.0` source version.

The published `1.4.0` GitHub Release intentionally reused the historical `1.4.0` tag. That tag still points to the older pre-consolidation commit, while the source tree has continued to carry version `1.4.0`. For supply-chain safety, this release does **not** force-move the published remote `1.4.0` tag or shadow it with a conflicting local tag.

Consequently, a raw Git comparison from the historical `1.4.0` tag to `1.4.1` includes older consolidation work already documented as part of the retrospective 1.4.0 release. This manifest records the actual post-consolidation patch scope that should be read as the 1.4.1 release notes.

## Included since the consolidated 1.4.0 source baseline

### Health, exposure and homelab observability

- #107 / #108: richer TrueNAS DNS, TCP, TLS and HTTP failure diagnostics.
- #109 / #110 / #111: explicit SSH/public-port policy, TrueNAS TLS semantics and reconciled exposure policy.
- #114 / #115: platform probe logging and dependency-aware health propagation.
- #118 / #120: TrueNAS connection-phase and WebSocket proxy-route diagnostics.
- #119: read-only pfSense DNS-resilience posture.
- #127 / #128: canonical TrueNAS `:7000` HTTPS listener and distinct HTTPS/API health labels.
- #129: staged TrueNAS diagnostics, required-dependency treatment, topology-based health-board grouping, provider credential-presence checks, outside-in production smoke tests and authoritative `nabla-compose` presentation/exposure consumption with last-known-good fallback.
- Follow-up hardening: encapsulate the homelab catalog cache state and serialize expired-cache refreshes so concurrent health/UI requests share one authoritative-source fetch.

### Runtime and developer tooling

- #122: project MCP integrations and FastAPI Cloud operational skill.
- #125: bounded, redacted, loopback-only local runtime diagnostics exposed through MCP tooling.
- #126: TrueNAS BETA.2 API-client alignment and GitHub MCP startup correction.

### CI, deployment and release reliability

- #106: release-version validation tolerates the intentionally empty npm lock metadata while preserving all other version checks.
- #112: production branch alignment on `master`.
- #121 / #123 / #124: FastAPI Cloud validation environment, documented project CLI invocation and Python 3.13 setup.
- #129: release-triggered immutable-tag deployment, reusable post-deploy smoke verification and deterministic package/deployment dispatch.
- Follow-up recovery: replace the incompatible local `1.4.0` retagging workaround with an explicit, retryable `1.4.1` recovery path that never rewrites the historical tag and returns to normal semantic-release after the baseline is repaired.

### Dependency/test maintenance

- #117: pytest 9 migration with async-test marker corrections.

## 1.4.1 release mechanics

The source deliberately remains synchronized at `1.4.0` until the one-time recovery release runs. The recovery path is intentionally separate from the normal semantic-release calculation because semantic-release refreshes remote tags internally and therefore cannot safely operate with a locally repointed `1.4.0` tag.

After the follow-up release fix is merged to `master`:

1. the workflow validates the synchronized checked-in source version and reads the latest published GitHub Release;
2. when both are `1.4.0`, it prepares **exactly `1.4.1`** without modifying the historical `1.4.0` tag;
3. npm metadata is updated with `npm version --no-git-tag-version`, while `scripts/set_release_version.py` updates the Python, uv and Docker version sources with exact-one replacement assertions;
4. `scripts/check_versions.py` must confirm that every version source is synchronized before the release commit can be pushed;
5. the workflow creates an immutable `1.4.1` tag and GitHub Release using this curated manifest, then emits the single `semantic-release-published` dispatch used by package publication and FastAPI Cloud deployment;
6. if a previous recovery attempt pushed the `1.4.1` release commit but failed before creating its tag or GitHub Release, a later run repairs only that exact state and refuses to repoint an existing mismatched tag;
7. after source and the published release are aligned at `1.4.1`, all future releases return to the normal Conventional Commit semantic-release path.

The release commit intentionally does not use `[skip ci]` for this one-time recovery. A second semantic-release run can therefore queue behind the first and repair a partial commit/tag publication if necessary. The normal semantic-release-generated release commits retain their existing `[skip ci]` behavior.

## Release gate

PR #129 was merged before its post-merge release gate completed. Its first Semantic Release run failed before publishing `1.4.1` because semantic-release rejected the locally repointed `1.4.0` tag while fetching the immutable remote tag (`would clobber existing tag`). No remote tag was rewritten by that failed run.

The follow-up candidate must therefore pass:

- Python startup, Ruff, Pylint, Bandit, full pytest and package build;
- Docker build and Trivy;
- MegaLinter including Zizmor, Checkov, secrets and formatting checks;
- CodeQL and GitGuardian;
- the homelab cache concurrency regression test;
- no new unresolved security/code-scanning findings.

After merge, require the one-time `1.4.1` release, package publication, FastAPI Cloud deployment and post-deploy production smoke workflows to complete successfully before considering `1.4.1` published.
