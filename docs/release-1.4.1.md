# 1.4.1 release manifest

## Purpose

`1.4.1` is the first patch release after the repository was consolidated back onto the checked-in `1.4.0` source version.

The published `1.4.0` GitHub Release intentionally reused the historical `1.4.0` tag. That tag still points to the older pre-consolidation commit, while the source tree has continued to carry version `1.4.0`. For supply-chain safety, this release does **not** force-move the published remote `1.4.0` tag.

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

### Runtime and developer tooling

- #122: project MCP integrations and FastAPI Cloud operational skill.
- #125: bounded, redacted, loopback-only local runtime diagnostics exposed through MCP tooling.
- #126: TrueNAS BETA.2 API-client alignment and GitHub MCP startup correction.

### CI, deployment and release reliability

- #106: release-version validation tolerates the intentionally empty npm lock metadata while preserving all other version checks.
- #112: production branch alignment on `master`.
- #121 / #123 / #124: FastAPI Cloud validation environment, documented project CLI invocation and Python 3.13 setup.
- #129: release-triggered immutable-tag deployment, reusable post-deploy smoke verification, deterministic package-publication dispatch and restored automatic semantic-release progression.

### Dependency/test maintenance

- #117: pytest 9 migration with async-test marker corrections.

## 1.4.1 release mechanics

The PR deliberately keeps checked-in versions at `1.4.0`. After merge to `master`:

1. the automatic semantic-release workflow validates that source and latest published release both report `1.4.0`;
2. for this one recovery release only, it moves the **local checkout's** `1.4.0` tag to the immediate pre-merge production baseline; the published remote tag is not rewritten;
3. the PR is represented by a `fix(...)` release commit, so the required next version is exactly `1.4.1`;
4. semantic-release updates all synchronized version sources, changelog metadata, the Git tag and GitHub Release atomically;
5. the `semantic-release-published` repository dispatch triggers both package publication and FastAPI Cloud deployment from the immutable `1.4.1` tag;
6. the reusable production smoke checks `/api/homelab/status` and verifies that the `/api` UI reports `1.4.1`.

After `1.4.1` exists, future semantic-release runs use that new immutable tag normally; the one-time local baseline repair becomes a no-op because source/latest release are no longer both `1.4.0`.

## Release gate

Do not mark the release candidate ready until all of the following pass on the final squashed PR head:

- Python startup, Ruff, Pylint, Bandit, full pytest and package build;
- Docker build and Trivy;
- MegaLinter including Zizmor, Checkov, secrets and formatting checks;
- CodeQL and GitGuardian;
- production smoke against the currently deployed release;
- no unresolved security/code-scanning review threads.

After merge, require the semantic-release, package publication, FastAPI Cloud deployment and post-deploy production smoke workflows to complete successfully before considering `1.4.1` published.
