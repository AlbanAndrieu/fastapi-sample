# syntax=docker/dockerfile:1

# dockerfile_lint - ignore
# hadolint ignore=DL3007
FROM python:3.12-slim AS python-base

LABEL name="fastapi-sample" vendor="sample" version="1.2.0" \
 description="Image used by our products to build python\
 this image is running on Python 3.12."

LABEL com.datadoghq.tags.service="fastapi-sample"
# LABEL com.datadoghq.tags.env="uat"
LABEL com.datadoghq.tags.version="1.1.0"

LABEL org.opencontainers.image.source=https://gitlab.com/AlbanAndrieu/fastapi-sample
LABEL org.opencontainers.image.description="My sample image"
LABEL org.opencontainers.image.licenses=MIT

# dockerfile_lint - ignore
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# No interactive frontend during docker build
ENV DEBIAN_FRONTEND=noninteractive \
    DEBCONF_NONINTERACTIVE_SEEN=true

ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8
ENV TERM="xterm-256color"

ARG DD_GIT_REPOSITORY_URL
ARG DD_GIT_COMMIT_SHA
ENV DD_GIT_REPOSITORY_URL=${DD_GIT_REPOSITORY_URL}
ENV DD_GIT_COMMIT_SHA=${DD_GIT_COMMIT_SHA}

ARG GITLAB_PIP_USER="gitlab-ci-token"

# Enable retry logic for apt up to 10 times
# Configure apt to always assume Y
# kics-scan ignore-line
RUN echo "APT::Acquire::Retries \"10\";" > /etc/apt/apt.conf.d/80-retries \
&& echo "APT::Get::Assume-Yes \"true\";" > /etc/apt/apt.conf.d/90assumeyes

# build-essential has gcc
# kics-scan ignore-line
# hadolint ignore=DL3008
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
  --mount=type=cache,target=/var/lib/apt,sharing=locked \
  apt-get update --fix-missing \
  && apt-get full-upgrade -y \
  && apt-get -y install --no-install-recommends build-essential \
  libpq-dev \
  locales tzdata curl \
  nano vim \
  net-tools bash && \
  apt-get clean && rm -rf /var/lib/apt/lists/*

# because of tzdata and the need of noninteractive
ENV TZ="Europe/Paris"
RUN echo "${TZ}" > /etc/timezone
RUN ln -fs /usr/share/zoneinfo/${TZ} /etc/localtime && locale-gen en_US.UTF-8 \
    && dpkg-reconfigure --frontend noninteractive tzdata

# Turns off buffering for easier container logging
# python
ENV PYTHONUNBUFFERED=1 \
    # prevents python creating .pyc files
    PYTHONDONTWRITEBYTECODE=1 \
    # pip
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    # uv (https://docs.astral.sh/uv/guides/integration/docker/)
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/tmp/uv_cache \
    # paths
    # this is where our requirements + virtual environment will live
    PYSETUP_PATH="/code" \
    VENV_PATH="/code/.venv"

# `builder-base` stage is used to build deps + create our virtual environment
FROM python-base AS builder-base

# Explicitly set user/group IDs
RUN groupadd -r jm-python --gid=999 && useradd -m -d ${PYSETUP_PATH} -r -g jm-python --uid=999 jm-python

RUN chown -R jm-python:jm-python ${PYSETUP_PATH}

# copy project requirement files here to ensure they will be cached.
WORKDIR ${PYSETUP_PATH}

# This is used by nuxt, its dependencies require OpenSSLv2 where node v20 uses OpenSSLv3
ARG NODE_VERSION=22
ENV NODE_OPTIONS="--openssl-legacy-provider"
ENV NODE_VERSION=${NODE_VERSION}

# hadolint ignore=DL3008,DL3015,DL3006,DL4006
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
  --mount=type=cache,target=/var/lib/apt,sharing=locked \
  curl -sL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - && \
  apt-get update && apt-get install --no-install-recommends -y nodejs=${NODE_VERSION}* && apt-get clean && rm -rf /var/lib/apt/lists/* && \
  npm set progress=false && \
  npm config set depth 0 && \
  npm install -g npm@11.12.1 && apt-get purge -y npm

COPY --chown=jm-python:jm-python package.json package-lock.json .npmrc ${PYSETUP_PATH}/

# USER jm-python

# hadolint ignore=SC3037
RUN --mount=type=secret,id=read-npm-token,uid=999,target=/run/secrets/CI_JOB_TOKEN \
  --mount=type=cache,target=/root/.npm,id=npm_cache \
  echo "@nabla-group:registry=https://gitlab.com/api/v4/packages/npm/" > ${PYSETUP_PATH}/.npmrc && \
  echo -e "'//gitlab.com/api/v4/packages/npm/:_authToken'=\"$(cat /run/secrets/CI_JOB_TOKEN)\"" >> ${PYSETUP_PATH}/.npmrc && \
  npm install --cache /root/.npm && npm cache clean --force && \
  rm -rf ~/.npmrc ${PYSETUP_PATH}/.npmrc ${PYSETUP_PATH}/.npm

USER root

COPY --from=ghcr.io/astral-sh/uv:0.8.14 /uv /usr/local/bin/uv

USER jm-python

COPY --chown=jm-python:jm-python pyproject.toml uv.lock ${PYSETUP_PATH}/

ENV PATH="${PYSETUP_PATH}/.local/bin/:${VENV_PATH}/bin:${PATH}"

USER root

# Dependency groups: see `[tool.uv].default-groups` in pyproject.toml.
# Private index: https://docs.astral.sh/uv/configuration/indexes/#providing-credentials
# Secret id must match CI: --secret id=read-package-token,env=CI_PIP_GITLABNABLA_TOKEN (see .gitlab-ci.yml DOCKER_BUILD_OPT)
RUN --mount=type=secret,id=read-package-token \
  --mount=type=cache,target=${UV_CACHE_DIR} \
  set -eux; \
  export UV_INDEX_GITLAB_DS_USERNAME=package_read; \
  UV_INDEX_GITLAB_DS_PASSWORD="$(cat /run/secrets/read-package-token)"; \
  export UV_INDEX_GITLAB_DS_PASSWORD; \
  uv sync --frozen --no-install-project; \
  uv pip install ansible==11.5.0; \
  chown -R jm-python:jm-python "${PYSETUP_PATH}/.venv"

USER jm-python

# dockerfile_lint - ignore
# hadolint ignore=DL3007
# `development` image is used during development / testing
FROM python-base AS development
ENV FASTAPI_ENV=development

WORKDIR ${PYSETUP_PATH}

# Explicitly set user/group IDs
RUN groupadd -r jm-python --gid=999 && useradd -m -d ${PYSETUP_PATH} -r -g jm-python --uid=999 jm-python

RUN chown -R jm-python:jm-python /code

COPY --from=builder-base "${PYSETUP_PATH}" "${PYSETUP_PATH}/"

# development stage is FROM python-base; builder's `uv` binary is not inherited
COPY --from=ghcr.io/astral-sh/uv:0.8.14 /uv /usr/local/bin/uv

USER jm-python

# Slim env vs builder: same intent as former `poetry install --no-root --with api,extra,...`
RUN --mount=type=secret,id=read-package-token \
  --mount=type=cache,target=${UV_CACHE_DIR} \
  set -eux; \
  export UV_INDEX_GITLAB_DS_USERNAME=package_read; \
  UV_INDEX_GITLAB_DS_PASSWORD="$(cat /run/secrets/read-package-token)"; \
  export UV_INDEX_GITLAB_DS_PASSWORD; \
  uv sync --frozen --no-install-project --no-default-groups \
    --group base \
    --group api \
    --group extra \
    --group open_telemetry \
    --group deployment \
    --group temporal

COPY --chown=jm-python:jm-python nabla/ "${PYSETUP_PATH}/jm-python/nabla/"
COPY --chown=jm-python:jm-python server_app.py "${PYSETUP_PATH}/jm-python/"
COPY --chown=jm-python:jm-python server_all.py "${PYSETUP_PATH}/jm-python/"

RUN mkdir -p "${PYSETUP_PATH}/jm-python/var/"

WORKDIR ${PYSETUP_PATH}/jm-python/

HEALTHCHECK CMD curl --fail http://localhost:8080/v1/ping || exit 1

EXPOSE 8080

CMD ["/code/.venv/bin/uvicorn", "--reload", "server_all:app", "--host", "0.0.0.0", "--port", "8080"]

# `production` image used for runtime
FROM python-base AS production
ENV FASTAPI_ENV=production

# This is used by nuxt, its dependencies require OpenSSLv2 where node v20 uses OpenSSLv3
ARG NODE_VERSION=20
ENV NODE_OPTIONS="--openssl-legacy-provider"
ENV NODE_VERSION=${NODE_VERSION}

# hadolint ignore=DL3008,DL3015,DL3006,DL4006
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
  --mount=type=cache,target=/var/lib/apt,sharing=locked \
  curl -sL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - && \
  apt-get update && apt-get install --no-install-recommends -y nodejs=${NODE_VERSION}* && apt-get clean && rm -rf /var/lib/apt/lists/* && \
  npm set progress=false && \
  npm config set depth 0 && \
  npm install -g npm@11.12.1 && apt-get purge -y npm

# Explicitly set user/group IDs
RUN groupadd -r jm-python --gid=999 && useradd -m -d ${PYSETUP_PATH} -r -g jm-python --uid=999 jm-python

RUN chown -R jm-python:jm-python ${PYSETUP_PATH}

USER jm-python

COPY --from=builder-base "${PYSETUP_PATH}" "${PYSETUP_PATH}/"

COPY --chown=jm-python:jm-python nabla/ "${PYSETUP_PATH}/jm-python/nabla/"
# COPY --chown=jm-python:jm-python server_app.py "${PYSETUP_PATH}/jm-python/"
COPY --chown=jm-python:jm-python server_all.py "${PYSETUP_PATH}/jm-python/"
COPY --chown=jm-python:jm-python my-login-app/ "${PYSETUP_PATH}/jm-python/my-login-app/"
COPY --chown=jm-python:jm-python templates/ "${PYSETUP_PATH}/jm-python/templates/"

ENV PATH="${PYSETUP_PATH}/.local/bin/:${VENV_PATH}/bin:${PATH}"

WORKDIR "${PYSETUP_PATH}/jm-python/"

EXPOSE 8080

# CMD ["/code/.venv/bin/uvicorn", "--reload", "server_all:app", "--host", "0.0.0.0", "--port", "8080"]

CMD [ \
    "ddtrace-run", \
    "gunicorn", "server_all:app", \
    "-k", "uvicorn_worker.UvicornWorker", \
    "--name", "fastapi-sample", \
    "--workers", "4", \
    "--threads", "1", \
    "--worker-connections", "1000", \
    "--max-requests", "1000", \
    "--max-requests-jitter", "100", \
    "--bind", "0.0.0.0:8080", \
    "--graceful-timeout", "120", \
    "--timeout", "120", \
    "--keep-alive", "5", \
    "--logger-class=nabla.utils.log_config.JMGunicornLogger", \
    "--log-level", "info", \
    "--access-logfile", "-" \
]

HEALTHCHECK --interval=1m --timeout=10s --start-period=60s --retries=5 \
    CMD curl --noproxy localhost -o /dev/null -sS http://localhost:8000/health || exit 1
