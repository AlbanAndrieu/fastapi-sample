# 1.5.8 — consolidated edge diagnostics and shared probe cache

Release `1.5.8` consolidates the code that was temporarily published as `1.6.0` and `1.7.0` after those GitHub Releases were removed. The Git history remains unchanged; only the maintained release baseline is repaired.

## Included changes

### Health and production diagnostics

- Expose edge evidence and resilient production diagnostics from PR #170 / commit `d69b3cf728e8f2bf91ebc6a524376cf7543aea01`.
- Preserve the pfSense, Snort, Cloudflare and TrueNAS observability improvements already present on `master`.
- Keep production health behavior read-only and sanitized.

### Shared external probe cache

- Share external probe results across replicas from PR #171 / commit `edc66db28df5d709bd62bbcf0bbb66e6d5eefa83`.
- Harden stale-last-known-good semantics, outcome-aware L1 TTL handling, Redis L2 primitives and pfSense probe observability from PR #172 / merge commit `dcc6e714136735381daf548d05df2a02499e155b`.
- Preserve the L1 + Redis L2 cache, distributed single-flight and stale-last-known-good behavior already present on `master`.

## Recovery contract

The release workflow may create `1.5.8` only from the exact recovery state where:

- the checked-in source version is still `1.7.0`;
- the latest published GitHub Release is `1.5.7`;
- remote tags `1.6.0`, `1.7.0` and `1.5.8` are absent.

The workflow then synchronizes npm, Python, uv and Docker version metadata to `1.5.8`, creates a dedicated `chore(release): 1.5.8` commit, pushes the immutable `1.5.8` tag and creates the GitHub Release from this document.

A retry path is allowed only when the synchronized `1.5.8` release commit is already at `master` while the latest published GitHub Release is still `1.5.7`. The obsolete tags must still be absent on every retry, and failure to verify their absence aborts recovery. It never force-moves an existing tag and refuses to publish if `1.5.8` points at a different commit.

After `1.5.8` is published, normal semantic-release progression resumes from that baseline.
