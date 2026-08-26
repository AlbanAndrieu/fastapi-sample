# 1.4.0 release reset

The repository is intentionally being consolidated back onto the `1.4.0` release baseline.

Before publishing the consolidated release:

1. Remove all semantic-version tags greater than `1.4.0`.
2. Merge the release-preparation pull request.
3. Recreate or retarget tag `1.4.0` so it points to the merged release commit rather than the historical `619ec9d10b1bc117aac8aa954774f7b4e66c608b` commit.
4. Publish the GitHub release from that tag only after CI and the FastAPI Cloud deployment are green.

The existing `1.4.0` tag must not be reused as-is because it currently points to the pre-consolidation code.
