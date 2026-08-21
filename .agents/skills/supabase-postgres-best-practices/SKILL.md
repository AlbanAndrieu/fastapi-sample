---
name: supabase-postgres-best-practices
description: Use for PostgreSQL query, schema, indexing, connection, RLS, locking, or performance work, especially on Supabase-hosted Postgres.
license: MIT
compatibility: Cursor, OpenCode, Codex, Copilot, Claude Code
metadata:
  scope: postgres
  load: on-demand
---

# Supabase Postgres best practices

Use this skill for PostgreSQL design and performance work. Load only the reference files relevant to the problem.

## Priority order

1. Query plans and missing/incorrect indexes.
2. Connection limits and pooling.
3. Security and RLS.
4. Schema design and constraints.
5. Locking/concurrency.
6. Data-access patterns.
7. Monitoring and maintenance.

## Workflow

- Inspect the actual query/schema before recommending indexes or rewrites.
- Prefer `EXPLAIN (ANALYZE, BUFFERS)` evidence for performance conclusions when available.
- Keep transactions short and avoid unnecessary lock scope.
- Avoid N+1 access patterns and unbounded offset pagination on large datasets.
- Treat RLS/security changes separately from pure performance optimization.
- Validate changes with representative queries/tests before declaring an optimization successful.

The detailed rules remain under `references/`; open only the files matching the current issue rather than loading the full reference corpus.
