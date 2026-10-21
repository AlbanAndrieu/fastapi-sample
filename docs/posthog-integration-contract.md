# PostHog integration contract (opt-in, privacy-first)

Status: proposed follow-up to the Cloud owner access recovery in PR #361. Do not enable new external event export while diagnosing the owner-access 403 incident.

## Purpose

Correlate user-visible catalog availability with deployment health. Existing Prometheus/Gatus and internal diagnostic metrics remain the source of truth for operational status; PostHog is for **aggregate product usage**, not probe evidence.

## Allowed events (future implementation)

| Event | Allowed properties |
| --- | --- |
| `catalog_loaded` | `app`, `environment`, `catalog_version`, `status`, `release` |
| `catalog_load_failed` | `app`, `environment`, `catalog_version`, `error_class`, `release` |
| `diagnostics_unlock_failed` | `app`, `environment`, `http_status`, `error_class` |

Fixed enums only for status and error_class; never send exception strings, endpoint URLs, path parameters, source IPs, CIDRs, tokens, cookies, user IDs, organization names or raw catalog contents.

## Acceptance gates before enabling

1. Explicit environment opt-in, default disabled; no credentials in repository or logs. Route ingestion to the existing EU PostHog project only after reviewing its data scope.
2. Shared event contract with `nabla-site-alban` and `nabla-site-bababou`; frontend emits catalog interaction events once, backend does **not** duplicate page events.
3. Unit tests with a mocked exporter verifying strict allowlists and no export for unknown event names/properties. Export failures must not impact API responses or diagnostics authorization.
4. Separate Preview/production; exclude localhost and tests; rate-limit and sample telemetry. Avoid exporting probe fan-out and internal topology.
5. Confirm GDPR lawful basis, retention, data processing terms, and minimization before production activation.

No change to `HOMELAB_TRUSTED_CIDRS`, restricted diagnostic responses or temporary public service inventory is authorized by this document.

Relevant documentation: https://posthog.com/docs/error-tracking/installation/python and https://posthog.com/docs/session-replay/privacy.
