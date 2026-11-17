# Temporary npm CLI bundled dependency risk acceptance (F04)

**Scope:** `fastapi-sample` PR #445, `package-lock.json` only. **Expires 2026-12-01.**

The full repository Trivy scan identifies two published medium-severity denial-of-service
advisories, [CVE-2026-118773](https://github.com/advisories/GHSA-3g3m-2fjr-6pw4)
for `glob` and [CVE-2026-118764](https://github.com/advisories/GHSA-g3hv-75wg-m249)
for `minimatch`.

## Remediation performed

- Non-bundled packages are now locked to `glob@14.0.6` and
  `minimatch@11.0.9` where a vulnerable major line was previously used.
- `npm ci --ignore-scripts` validated the regenerated lockfile.
- Only npm CLI's **bundled development-only copies** remain, under
  `node_modules/npm/node_modules/glob@13.0.6` and
  `node_modules/npm/node_modules/minimatch@10.2.5`.
- The CLI is pulled transitively by `semantic-release` through
  `@semantic-release/npm`. Neither bundled package is an application
  runtime dependency. The upstream vendor has not yet shipped fixed bundles:
  [npm/cli #10299](https://github.com/npm/cli/issues/10299).

## Compensating controls

The two `.trivyignore.yaml` entries match **CVE + exact npm PURL +
package-lock.json**, expire on 2026-12-01, and keep Trivy blocking on all
other findings. The always-on
`tests/unit/test_npm_bundled_vulnerability_guard.py` rejects any other
vulnerable `glob` or `minimatch` instance, any non-development or unbundled
instance, and expired or overbroad exceptions.

Risk: the package manager executes in controlled CI/release tooling, not in
the deployed FastAPI application. A malicious file pattern could still trigger
a build-time denial of service; never run untrusted patterns in that workflow.

**Required follow-up:** when npm bundles patched versions, regenerate the
lockfile and remove both exceptions and this temporary acceptance. If no
patched upstream is available before expiry, CI must block pending a new
explicit security review; do not extend silently.
