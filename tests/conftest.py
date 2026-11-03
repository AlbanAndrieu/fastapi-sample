"""Shared pytest bootstrap for unit and integration tests."""

import os

# Test modules import application settings at collection time. Keep that import
# hermetic by providing the same non-secret defaults as the Python CI workflow.
os.environ.setdefault("KEYCLOAK_SERVER_URL", "http://localhost:8080")
os.environ.setdefault("KEYCLOAK_REALM", "test")
os.environ.setdefault("KEYCLOAK_CLIENT_ID", "test")
os.environ.setdefault("KEYCLOAK_CLIENT_SECRET", "test-secret")
os.environ.setdefault("OAUTH_TOKEN_SECRET", "mocked-oauth-token-secret")

# Never let a developer's shell/runtime telemetry configuration leak into
# tests. Tests that exercise telemetry configuration can still monkeypatch these
# variables explicitly after collection.
for key in (
    "METRICS_ENABLED",
    "LOGFIRE_ENABLED",
    "SENTRY_ENABLED",
    "DATADOG_ENABLED",
    "UNLEASH_ENABLED",
    "STATSIG_ENABLED",
    "DD_TRACE_ENABLED",
    "DD_PROFILING_ENABLED",
):
    os.environ[key] = "false"
os.environ["LOGFIRE_TOKEN"] = ""
os.environ["SENTRY_DSN"] = ""
os.environ["SENTRY_LOCAL_DSN"] = ""
os.environ["UNLEASH_INSTANCE_ID"] = ""
os.environ["STATSIG_API_KEY"] = ""

# Security tests retain the fail-closed baseline unless a test opts in.
os.environ["HOMELAB_PUBLIC_DIAGNOSTICS_READONLY"] = "false"

# Git hooks export GIT_DIR/GIT_INDEX_FILE: tests that build throwaway repositories
# would otherwise write into the real checkout's index. List: git rev-parse --local-env-vars.
for key in (
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_DIR",
    "GIT_GRAFT_FILE",
    "GIT_IMPLICIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_PREFIX",
    "GIT_SHALLOW_FILE",
    "GIT_WORK_TREE",
):
    os.environ.pop(key, None)
