# syntax=docker/dockerfile:1

FROM python:3.13-slim-trixie AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/tmp/uv_cache \
    PYSETUP_PATH=/code \
    VENV_PATH=/code/.venv

WORKDIR /code

# uv delegates Git-backed dependencies to the Git executable. Keep Git confined
# to the builder stage so the production image remains minimal. These transient
# build tools intentionally track the security-updated packages from the pinned
# Debian release instead of coupling the build to repository snapshot versions.
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.8.14 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./

# Install only runtime groups. The package-read secret is optional so a normal
# `docker compose build` works for the public dependency graph. Environments
# that require the private GitLab index can still inject the BuildKit secret.
RUN --mount=type=secret,id=read-package-token,required=false \
    --mount=type=cache,target=/tmp/uv_cache \
    set -eux; \
    if [ -s /run/secrets/read-package-token ]; then \
      export UV_INDEX_GITLAB_DS_USERNAME=package_read; \
      UV_INDEX_GITLAB_DS_PASSWORD="$(cat /run/secrets/read-package-token)"; \
      export UV_INDEX_GITLAB_DS_PASSWORD; \
    fi; \
    uv sync --frozen --no-install-project --no-default-groups \
      --group base \
      --group api \
      --group api-extra \
      --group api-ai \
      --group api-tracing \
      --group db \
      --group deployment \
      --group encryption \
      --group open_telemetry \
      --group panda \
      --group temporal; \
    /code/.venv/bin/python -c "import cloudflare, ddtrace, truenas_api_client"

FROM python:3.13-slim-trixie AS production

ARG APP_VERSION="1.4.8"

LABEL name="fastapi-sample" \
      vendor="sample" \
      org.opencontainers.image.source="https://github.com/AlbanAndrieu/fastapi-sample" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${APP_VERSION}"

ENV FASTAPI_ENV=production \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYSETUP_PATH=/code \
    VENV_PATH=/code/.venv \
    PATH=/code/.venv/bin:$PATH \
    WEB_CONCURRENCY=1 \
    DATADOG_ENABLED=false \
    DD_TRACE_ENABLED=false \
    DD_PROFILING_ENABLED=false \
    DD_LOGS_INJECTION=false \
    DD_APPSEC_ENABLED=false \
    DD_IAST_ENABLED=false

# Runtime libraries only. Compiler toolchain, Node/npm, editors, network tools,
# pytest and Ansible deliberately stay out of the production image. Versions are
# pinned to Debian 13 (trixie) packages so the image remains reproducible.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl=8.14.1-2+deb13u4 \
        libpq5=17.10-0+deb13u1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 999 jm-python \
    && useradd --system --uid 999 --gid jm-python --home-dir /code jm-python \
    && mkdir -p /code/jm-python/var \
    && chown -R jm-python:jm-python /code

COPY --from=builder --chown=jm-python:jm-python /code/.venv /code/.venv
COPY --chown=jm-python:jm-python nabla/ /code/jm-python/nabla/
COPY --chown=jm-python:jm-python server_all.py /code/jm-python/
COPY --chown=jm-python:jm-python my-login-app/ /code/jm-python/my-login-app/
COPY --chown=jm-python:jm-python templates/ /code/jm-python/templates/

USER 999:999
WORKDIR /code/jm-python

EXPOSE 8080

HEALTHCHECK --interval=1m --timeout=10s --start-period=60s --retries=5 \
    CMD ["curl", "--fail", "--silent", "--show-error", "http://localhost:8080/health"]

CMD ["gunicorn", "server_all:app", "-k", "uvicorn_worker.UvicornWorker", "--name", "fastapi-sample", "--threads", "1", "--worker-connections", "1000", "--max-requests", "1000", "--max-requests-jitter", "100", "--bind", "0.0.0.0:8080", "--graceful-timeout", "120", "--timeout", "120", "--keep-alive", "5", "--logger-class=nabla.utils.log_config.JMGunicornLogger", "--log-level", "info", "--access-logfile", "-"]
