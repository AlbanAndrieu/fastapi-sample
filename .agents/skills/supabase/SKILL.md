---
name: supabase
description: Use for Supabase Database, Auth, Storage, Realtime, Edge Functions, RLS, migrations, Supabase CLI, or Supabase MCP tasks.
license: MIT
compatibility: Cursor, OpenCode, Codex, Copilot, Claude Code
metadata:
  scope: database-platform
  load: on-demand
---

# Supabase

Use this skill only for Supabase-specific work.

## Workflow

1. Inspect the repository's current Supabase integration, migrations, and environment model.
2. Verify current Supabase documentation for version-sensitive APIs and CLI commands.
3. Never expose `service_role`/secret keys to clients, logs, or generated examples.
4. For exposed schemas, treat RLS and explicit authorization predicates as mandatory security boundaries.
5. Prefer project-local migration conventions over inventing a new schema workflow.
6. Validate schema/security changes with focused tests or SQL checks and run advisors when available.
7. Use the Supabase MCP/CLI only when it materially reduces manual work; do not preload large documentation sets.

## Security invariants

- Do not authorize from user-editable metadata.
- `TO authenticated` alone is not row-level authorization; include ownership/permission predicates.
- UPDATE policies normally need both `USING` and `WITH CHECK`.
- Treat `SECURITY DEFINER` as privileged and exceptional.
- Keep privileged functions out of exposed schemas unless explicitly secured.

For detailed PostgreSQL performance guidance, use the separate `supabase-postgres-best-practices` skill.
