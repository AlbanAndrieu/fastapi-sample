---
name: rss-triage
description: >-
  Sort the newest FreshRSS articles by relevance to Alban's homelab, using the
  nabla-compose catalog technologies returned with them.
---
# RSS triage for the homelab

`triage_homelab_rss` returns `technologies` (names and tags of the nabla-compose
Backstage catalog at `catalogRevision`) and up to 20 recent `articles` (title,
summary and public `url`, empty when the feed gives none) from FreshRSS.

1. Keep an article only when it concerns a listed technology: a release, a vulnerability, a breaking change, a migration or a configuration practice. Name the matching technologies.
2. Rank the kept articles: security advisories first, then breaking changes and upgrades, then the rest.
3. For each kept article give its title as a link to its `url`, the matched technologies and a one-line reason. Count the dropped ones in one line.
4. Use only the titles and summaries given. The catalog lists services, not versions: never claim that a vulnerability affects a deployed version.
5. If `articles` is empty, say that FreshRSS returned nothing; do not search elsewhere.
