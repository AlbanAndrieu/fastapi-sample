# GitHub repository rulesets

`main.json` is an importable GitHub repository ruleset for the default branch.

## Import

1. Open **Settings → Rules → Rulesets**.
2. Select **New ruleset → Import a ruleset**.
3. Import `.github/rulesets/main.json`.
4. Keep the imported ruleset **Disabled** until the semantic-release bypass below is configured.

## Required checks

The ruleset requires these pull-request checks:

- `Test and build Python package`
- `Docker CI / Build Docker`
- `MegaLinter / MegaLinter`

The strict status-check policy is enabled, so a pull request must be tested against the latest `main` before it can merge.

The ruleset also:

- requires changes to `main` to arrive through a pull request;
- allows only squash merges, preserving a linear `main` history and making the PR title the release-relevant commit subject;
- requires review conversations to be resolved;
- prevents force pushes;
- prevents deletion of `main`.

No approving review is required because this is currently a single-maintainer repository and auto-merge should not be blocked waiting for another reviewer.

## Important: semantic-release bypass

The semantic-release workflow currently creates and pushes a release commit directly to `main` after a PR is merged. Once this ruleset is active, that push is intentionally blocked unless the release identity can bypass the ruleset.

Do **not** grant a broad bypass to every administrator or writer just to make semantic-release work.

Recommended setup:

1. Create/install a dedicated GitHub App for semantic-release with only the repository permissions needed by the release workflow.
2. In the imported ruleset, under **Bypass list**, add that GitHub App with **Always allow**.
3. Change `.github/workflows/semantic-release.yml` to authenticate its release push with an installation token from that app instead of the default `GITHUB_TOKEN`.
4. Only then change the ruleset enforcement from **Disabled** to **Active**.

The default GitHub Actions `GITHUB_TOKEN` should not be assumed to bypass repository rulesets. Keeping the ruleset disabled at import time prevents an accidental release outage while this release identity is being migrated.

## Auto-merge

With repository **Allow auto-merge** enabled, select **Enable auto-merge → Squash and merge** on a pull request. GitHub will merge it automatically after the required checks above are successful, the branch is up to date with `main`, and all review conversations are resolved.
