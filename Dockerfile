# syntax=docker/dockerfile:1.5

# dockerfile_lint - ignore
# hadolint ignore=DL3007
# FROM pytorch/pytorch:1.13.1-cuda11.6-cudnn8-runtime as prebuild
# FROM pytorch/pytorch:1.13.0-cuda11.6-cudnn8-runtime as prebuild
# FROM pytorch/pytorch:1.7.1-cuda11.0-cudnn8-runtime as prebuild
FROM python:3.10-slim AS python-base

LABEL name="fastapi-sample" vendor="sample" version="1.0.1" \
 description="Image used by our products to build python\
 this image is running on Ubuntu 22.10."

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# No interactive frontend during docker build
ENV DEBIAN_FRONTEND=noninteractive \
    DEBCONF_NONINTERACTIVE_SEEN=true

ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8
ENV TERM="xterm-256color"

ARG CI_PIP_GITLABJUSMUNDI_TOKEN
ENV CI_PIP_GITLABJUSMUNDI_TOKEN=${CI_PIP_GITLABJUSMUNDI_TOKEN:-""}

# Enable retry logic for apt up to 10 times
# Configure apt to always assume Y
# kics-scan ignore-line
RUN echo "APT::Acquire::Retries \"10\";" > /etc/apt/apt.conf.d/80-retries \
&& echo "APT::Get::Assume-Yes \"true\";" > /etc/apt/apt.conf.d/90assumeyes

# build-essential has gcc
# kics-scan ignore-line
# hadolint ignore=DL3008
RUN apt-get update && \
    apt-get -y install --no-install-recommends build-essential \
    locales tzdata curl && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# because of tzdata and the need of noninteractive
ENV TZ "Europe/Paris"
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
    # poetry
    # https://python-poetry.org/docs/configuration/#using-environment-variables
    POETRY_VERSION=1.7.1 \
    # make poetry install to this location
    POETRY_HOME="/opt/poetry" \
    POETRY_NO_INTERACTION=1 \
    # make poetry create the virtual environment in the project's root
    # it gets named `.venv`
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    # do not ask any interactive question
    POETRY_NO_INTERACTION=1 \
    # paths
    # this is where our requirements + virtual environment will live
    # PYSETUP_PATH="/opt/pysetup" \
    PYSETUP_PATH="/code" \
    VENV_PATH="/code/.venv"

# prepend poetry and venv to path
ENV PATH="$POETRY_HOME/bin:$VENV_PATH/bin:$PATH"

# `builder-base` stage is used to build deps + create our virtual environment
FROM python-base as builder-base

# Explicitly set user/group IDs
RUN groupadd -r jm-python --gid=999 && useradd -m -d /code -r -g jm-python --uid=999 jm-python

RUN chown -R jm-python:jm-python /code

ENV PATH="$PATH:$VENV_PATH:$POETRY_HOME/bin"

# copy project requirement files here to ensure they will be cached.
WORKDIR $PYSETUP_PATH
# WORKDIR /code

# poetry 1.3.2
# hadolint ignore=DL3008
#RUN apt-get update && \
#    apt-get -y install --no-install-recommends python3-poetry && \
#    apt-get clean && rm -rf /var/lib/apt/lists/*
# install poetry - respects $POETRY_VERSION & $POETRY_HOME
RUN curl -sSL https://install.python-poetry.org | python3 -

USER jm-python

COPY --chown=jm-python:jm-python pyproject.toml poetry.lock $PYSETUP_PATH/

# RUN python -m venv $PYSETUP_PATH/.venv

ENV PATH=$PYSETUP_PATH/.local/bin/:${PATH}

# upgrade poetry version 1.7.1
# /code/.local/bin/poetry

# hadolint ignore=DL3013, DL3042
RUN python -m pip install --no-cache-dir --upgrade pip==23.3.2 &&\
    python -m pip install --no-cache-dir --upgrade poetry=="$POETRY_VERSION"

# RUN pip install poetry -U

RUN poetry config http-basic.gitlab package_read "$CI_PIP_GITLABJUSMUNDI_TOKEN" &&\
    poetry install --no-root --with deployment,open_telemetry,temporal # --no-dev --remove-untracked

# dockerfile_lint - ignore
# hadolint ignore=DL3007
# `development` image is used during development / testing
FROM python-base as development
ENV FASTAPI_ENV=development

WORKDIR $PYSETUP_PATH

# Explicitly set user/group IDs
RUN groupadd -r jm-python --gid=999 && useradd -m -d /code -r -g jm-python --uid=999 jm-python

RUN chown -R jm-python:jm-python /code

# copy in our built poetry + venv
COPY --from=builder-base $POETRY_HOME $POETRY_HOME
COPY --from=builder-base $PYSETUP_PATH $PYSETUP_PATH

USER jm-python

# quicker install as runtime deps are already installed
RUN poetry --no-root install --with deployment,open_telemetry,temporal,test,api

COPY --chown=jm-python:jm-python nabla/ $PYSETUP_PATH/jm-python/nabla/
COPY --chown=jm-python:jm-python serve.py $PYSETUP_PATH/jm-python/

RUN mkdir -p "$PYSETUP_PATH/jm-python/var/"

# ENV PATH=$PYSETUP_PATH/.venv/bin/:${PATH}

WORKDIR $PYSETUP_PATH/jm-python/

HEALTHCHECK CMD curl --fail http://localhost:8080/v1/ping || exit 1

EXPOSE 8080

CMD ["/code/.venv/bin/uvicorn", "--reload", "serve:app", "--host", "0.0.0.0", "--port", "8080"]

# `production` image used for runtime
FROM python-base as production
ENV FASTAPI_ENV=production

# Explicitly set user/group IDs
RUN groupadd -r jm-python --gid=999 && useradd -m -d /code -r -g jm-python --uid=999 jm-python

RUN chown -R jm-python:jm-python /code

USER jm-python

COPY --from=builder-base $PYSETUP_PATH $PYSETUP_PATH

COPY --chown=jm-python:jm-python nabla/ $PYSETUP_PATH/jm-python/nabla/
COPY --chown=jm-python:jm-python serve.py $PYSETUP_PATH/jm-python/

# ENV PATH=$PYSETUP_PATH/.venv/bin/:${PATH}

WORKDIR $PYSETUP_PATH/jm-python/

HEALTHCHECK CMD curl --fail http://localhost:8080/v1/ping || exit 1

EXPOSE 8080

# CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "serve:app", "--host", "0.0.0.0", "--port", "8080"]
CMD ["/code/.venv/bin/uvicorn", "--reload", "serve:app", "--host", "0.0.0.0", "--port", "8080"]
