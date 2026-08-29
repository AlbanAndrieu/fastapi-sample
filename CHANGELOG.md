## [1.4.3](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.4.2...1.4.3) (2026-08-29)


### Bug Fixes

* **release:** align trusted publisher OIDC claims ([#133](https://github.com/AlbanAndrieu/fastapi-sample/issues/133)) ([55e88ec](https://github.com/AlbanAndrieu/fastapi-sample/commit/55e88ecc40d5865ae629e329bef27c489f924e0a))

## [1.4.2](https://github.com/AlbanAndrieu/fastapi-sample/compare/1.4.1...1.4.2) (2026-08-28)


### Bug Fixes

* **release:** harden post-1.4.1 publishing ([#131](https://github.com/AlbanAndrieu/fastapi-sample/issues/131)) ([4bd9737](https://github.com/AlbanAndrieu/fastapi-sample/commit/4bd9737a2efdad048a2bcf512b55a57bf0be1f7c))

# Changelog

## 1.4.1 — homelab diagnostics and release recovery (2026-08-29)

### Health, security and observability

- Add ordered TrueNAS DNS, TCP, TLS, HTTPS, WebSocket, authentication and API diagnostics with explicit required-dependency failures.
- Reconcile service availability and exposure policy using the authoritative `nabla-compose` catalog with validated last-known-good/bootstrap fallback behavior.
- Expose only sanitized provider credential-presence state and improve pfSense/Cloudflare/TrueNAS diagnostics without leaking secret material.
- Group the API health board by topology/blast radius and preserve service metadata, icons and policy-aware Sickz behavior.
- Encapsulate homelab catalog cache state and serialize expired-cache refreshes so concurrent health/UI requests share one authoritative-source request.

### CI, release and deployment

- Reuse an outside-in production smoke workflow after immutable-tag FastAPI Cloud deployments.
- Keep Python 3.13, version-consistency, Docker/Trivy, MegaLinter and code-scanning gates in the release path.
- Replace the incompatible local `1.4.0` retagging workaround with a deterministic, retryable `1.4.1` recovery that never rewrites the historical remote tag.
- Synchronize explicit recovery versions across npm, Python, uv and Docker metadata with exact-match assertions before publishing.
- Return to normal Conventional Commit semantic-release progression after `1.4.1` establishes the new immutable release baseline.

## 1.4.0 — consolidated release (2026-08-27)

This release intentionally consolidates the work that was temporarily published under versions greater than `1.4.0`. Those GitHub releases were removed and the project is being realigned on `1.4.0` as the release baseline.

### Runtime, deployment and packaging

- Standardize supported runtime and CI on Python 3.13, including FastAPI Cloud and Docker.
- Harden FastAPI Cloud deployment metadata, runtime detection, health endpoints and production entrypoints.
- Keep Docker runtime minimal and align application version metadata across Python, npm and OCI images.
- Align local/MCP serving ports and deployment configuration, including the 8091 local MCP compatibility work.
- Reduce Vercel deployment scope and improve runtime/route handling.
- Harden semantic-release, release-baseline validation, GitHub release publication and version synchronization.
- Improve dependency, Renovate, CodeQL, MegaLinter, pre-commit and repository quality workflows.

### Homelab catalog and topology

- Introduce the typed homelab service catalog and validated topology APIs.
- Preserve service IDs, icons, internal endpoints, external exposure intent and security metadata.
- Make FastAPI the authoritative exposure-policy source and add explicit exposure overrides where required.
- Reconcile declared services with TrueNAS runtime/application inventory.
- Add application lifecycle observations and cached TrueNAS runtime snapshots.
- Add public homelab health APIs and split internal versus external observations.

### TrueNAS

- Add the TrueNAS dependency health signal and the read-only TrueNAS 26 API client integration.
- Consolidate TrueNAS URL handling around `TRUENAS_URL` with `https://truenas.albandrieu.com:7000` as the default.
- Add runtime/application inventory checks, caching and stale-result handling.
- Make TrueNAS required infrastructure in the production health board while distinguishing public ingress, optional internal TCP and authenticated API evidence.
- Add explicit INFO logging of the effective `TRUENAS_URL` to diagnose FastAPI Cloud connectivity.

### Exposure security, Sickz and Cloudflare

- Split Sickz from generic availability health and turn it into exposure-policy validation.
- Verify declared `external` and `tunnelSecure` intent against HTTP reachability, TLS trust and Cloudflare evidence.
- Add the read-only Cloudflare Tunnel observer and reconcile tunnel observations with declared service posture.
- Detect private services that unexpectedly become externally reachable or gain Cloudflare ingress.
- Verify Cloudflare-protected public services and report uncertain observer states separately.
- Preserve explicit direct `.int.albandrieu.com` exposure as a security warning rather than silently treating it as secure.
- Add protocol-aware pfSense/public-port policy checks, including SSH, LiteLLM and TrueNAS exposure expectations.
- Correct the LiteLLM public-policy port from 4100 to 4000.
- Detect application-level failure payloads even when an endpoint returns an HTTP success status.

### Health board and UI

- Refactor the health subsystem into focused platform, integration, observability, homelab and Sickz modules.
- Add reconciled service-health evidence and distinguish availability health from security-policy compliance.
- Improve refresh diagnostics, stale-state handling and required-infrastructure reporting.
- Split API JavaScript and CSS assets by responsibility and simplify the API page implementation.
- Improve Sickz status rendering, TLS indicators, Cloudflare evidence and pfSense port-policy presentation.
- Add OpenGraph/runtime presentation improvements and preserve service icons in the topology UI.

### Observability and robustness

- Simplify Logfire/FastAPI Cloud integration and keep observability integrations optional when disabled.
- Isolate Datadog runtime lifecycle and make it optional for FastAPI Cloud.
- Improve Sentry, Redis and optional integration health handling.
- Harden logging formatters and stream handlers against malformed records.
- Refactor Redis async lifecycle and failure handling.
- Improve notes persistence/queue error isolation and application startup/shutdown robustness.

### Architecture and maintainability

- Split oversized health, UI, configuration and integration modules into focused components.
- Introduce reusable FastAPI, homelab-service-contract and Redis lifecycle skills/rules for coding agents.
- Add feature flags, access-control helpers and environment/runtime abstractions.
- Consolidate engineering roadmap and health/environment documentation.
- Preserve the project line-count quality contract rather than relaxing oversized-module thresholds.

### Included post-1.4.0 work

The consolidation includes the changes previously represented by the temporary `1.4.1`, `1.5.x`, `1.6.x`, `1.7.x` and `1.8.x` release history, notably PRs #45–#101 and their follow-up fixes/refactors. The Git commit history remains the authoritative detailed audit trail.

---

## Historical releases before 1.4.0

Detailed pre-1.4.0 release history remains available in Git history and the tags `1.0.0` through `1.3.8`. The consolidated `1.4.0` entry above is now the maintained release baseline.
