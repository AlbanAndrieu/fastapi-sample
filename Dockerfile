# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/tmp/uv_cache \
    PYSETUP_PATH=/code \
    VENV_PATH=/code/.venv

WORKDIR /code

COPY --from=ghcr.io/astral-sh/uv:0.8.14 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./

# Install only runtime groups. In particular, do not install the default/dev,
# test or extra groups: those contain pytest, Ansible and other CI tooling.
RUN --mount=type=secret,id=read-package-token \
    --mount=type=cache,target=/tmp/uv_cache \
    set -eux; \
    export UV_INDEX_GITLAB_DS_USERNAME=package_read; \
    UV_INDEX_GITLAB_DS_PASSWORD="$(cat /run/secrets/read-package-token)"; \
    export UV_INDEX_GITLAB_DS_PASSWORD; \
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
    /code/.venv/bin/python -c "import ddtrace"

FROM python:3.12-slim AS production

LABEL name="fastapi-sample" \
      vendor="sample" \
      org.opencontainers.image.source="https://github.com/AlbanAndrieu/fastapi-sample" \
      org.opencontainers.image.licenses="MIT"

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
# pytest and Ansible deliberately stay out of the production image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libpq5 \
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

USER jm-python
WORKDIR /code/jm-python

EXPOSE 8080

HEALTHCHECK --interval=1m --timeout=10s --start-period=60s --retries=5 \
    CMD curl --fail --silent --show-error http://localhost:8080/health >/dev/null || exit 1

CMD ["gunicorn", "server_all:app", "-k", "uvicorn_worker.UvicornWorker", "--name", "fastapi-sample", "--threads", "1", "--worker-connections", "1000", "--max-requests", "1000", "--max-requests-jitter", "100", "--bind", "0.0.0.0:8080", "--graceful-timeout", "120", "--timeout", "120", "--keep-alive", "5", "--logger-class=nabla.utils.log_config.JMGunicornLogger", "--log-level", "info", "--access-logfile", "-"]
