# GitHub repository rulesets

`main.json` is an importable GitHub repository ruleset for the default branch.

## Import

1. Open **Settings → Rules → Rulesets**.
2. Select **New ruleset → Import a ruleset**.
3. Import `.github/rulesets/main.json`.
4. Keep the imported ruleset **Disabled** until the semantic-release App below is configured.

## Required checks

The ruleset requires these pull-request checks:

- `Test and build Python package`
- `Docker CI / Build Docker`
- `MegaLinter / MegaLinter`

Each required status check is pinned to the official GitHub Actions integration (`integration_id: 15368`). This prevents an unrelated integration from satisfying a protected-branch requirement by publishing a status with the same context name.

The strict status-check policy is enabled, so a pull request must be tested against the latest `main` before it can merge.

The ruleset also:

- requires changes to `main` to arrive through a pull request;
- allows only squash merges, preserving a linear `main` history and making the PR title the release-relevant commit subject;
- requires review conversations to be resolved;
- prevents force pushes;
- prevents deletion of `main`.

No approving review is required because this is currently a single-maintainer repository and auto-merge should not be blocked waiting for another reviewer. If a second regular maintainer is added later, increase `required_approving_review_count` to `1`, enable stale-review dismissal, and consider requiring approval of the last push.

## Important: semantic-release bypass

The semantic-release workflow creates and pushes a release commit directly to `main` after a PR is merged. Once this ruleset is active, that push is intentionally blocked unless the release identity can bypass the ruleset.

Do **not** grant a broad bypass to every administrator, writer, or to unrelated automation just to make semantic-release work. Use a dedicated GitHub App so only the release identity gets the bypass.

### 1. Create the release GitHub App

Create a GitHub App dedicated to this repository and grant only these repository permissions:

- **Contents: Read and write** — release commit, tag and GitHub Release;
- **Issues: Read and write** — semantic-release release notes/comments when used;
- **Pull requests: Read and write** — semantic-release PR-related operations.

Install the App only on `AlbanAndrieu/fastapi-sample`.

### 2. Configure the repository credentials

Add the App Client ID as a repository **Actions variable**:

- `RELEASE_APP_CLIENT_ID`

Add its private key as a repository **Actions secret**:

- `RELEASE_APP_PRIVATE_KEY`

`.github/workflows/semantic-release.yml` already detects these values and creates a short-lived installation token with `actions/create-github-app-token`. Until both values exist, it deliberately falls back to the normal `GITHUB_TOKEN`, which keeps releases working while the ruleset is still disabled.

### 3. Add the App to the ruleset bypass list

In **Settings → Rules → Rulesets → Protect main → Bypass list**, add the dedicated release GitHub App with **Always allow**.

Do not add the general GitHub Actions identity as the release bypass. The objective is to give bypass authority only to the dedicated release identity, not to every workflow in the repository.

### 4. Activate only after validation

Before changing enforcement to **Active**, verify that:

1. `Test and build Python package` is green;
2. `Docker CI / Build Docker` is green;
3. `MegaLinter / MegaLinter` is green;
4. `RELEASE_APP_CLIENT_ID` and `RELEASE_APP_PRIVATE_KEY` are configured;
5. the dedicated release App is present in the ruleset bypass list.

Then change the live ruleset enforcement from **Disabled** to **Active**.

The source-controlled `main.json` intentionally remains `disabled`: importing or reapplying the file must not accidentally activate branch protection before the release App is configured.

## Auto-merge

With repository **Allow auto-merge** enabled, select **Enable auto-merge → Squash and merge** on a pull request. GitHub will merge it automatically after the required checks above are successful, the branch is up to date with `main`, and all review conversations are resolved.
