# syntax=docker/dockerfile:1.5

# dockerfile_lint - ignore
# hadolint ignore=DL3007
# FROM pytorch/pytorch:1.13.1-cuda11.6-cudnn8-runtime as prebuild
# FROM pytorch/pytorch:1.13.0-cuda11.6-cudnn8-runtime as prebuild
# FROM pytorch/pytorch:1.7.1-cuda11.0-cudnn8-runtime as prebuild
FROM python:3.10

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
RUN echo "APT::Acquire::Retries \"10\";" > /etc/apt/apt.conf.d/80-retries \
&& echo "APT::Get::Assume-Yes \"true\";" > /etc/apt/apt.conf.d/90assumeyes

# build-essential has gcc
# hadolint ignore=DL3008
RUN apt-get update && \
    apt-get -y install --no-install-recommends build-essential git locales tzdata && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# because of tzdata and the need of noninteractive
ENV TZ "Europe/Paris"
RUN echo "${TZ}" > /etc/timezone
RUN ln -fs /usr/share/zoneinfo/${TZ} /etc/localtime && locale-gen en_US.UTF-8 \
    && dpkg-reconfigure --frontend noninteractive tzdata

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=off

# Explicitly set user/group IDs
RUN groupadd -r jm-python --gid=999 && useradd -m -d /code -r -g jm-python --uid=999 jm-python

RUN chown -R jm-python:jm-python /code

WORKDIR /code

ENV POETRY_HOME="/root/.local" \
    POETRY_NO_INTERACTION=1 \
    POETRY_VERSION=1.7.1 \
    VIRTUAL_ENV="/code/.venv"
# ENV POETRY_VERSION=${POETRY_VERSION:-"1.1.14+dfsg-1ubuntu1"}
ENV PATH="$PATH:$VIRTUAL_ENV:$POETRY_HOME/bin"

# hadolint ignore=DL3008
RUN apt-get update && \
    apt-get -y install --no-install-recommends python3-poetry && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

USER jm-python

COPY --chown=jm-python:jm-python pyproject.toml /code/
COPY --chown=jm-python:jm-python poetry.lock /code/

RUN python -m venv /code/.venv

# hadolint ignore=DL3013, DL3042
#RUN python -m pip install --no-cache-dir --upgrade pip &&\
#    python -m pip install --no-cache-dir --user --upgrade poetry==$POETRY_VERSION

RUN which poetry

RUN poetry config http-basic.gitlab package_read $CI_PIP_GITLABJUSMUNDI_TOKEN &&\
    poetry install --with deployment,temporal --no-root

# dockerfile_lint - ignore
# hadolint ignore=DL3007
# FROM prebuild as runtime

USER jm-python

COPY --chown=jm-python:jm-python nabla/ /code/jm-python/nabla/
COPY --chown=jm-python:jm-python serve.py /code/jm-python/

RUN mkdir -p /code/jm-python/var/

ENV PATH=/code/.venv/bin/:${PATH}

WORKDIR /code/jm-python

# HEALTHCHECK NONE
HEALTHCHECK CMD curl --fail http://localhost:8080/v1/ping || exit 1

EXPOSE 8080

CMD ["/code/.venv/bin/uvicorn", "serve:app", "--host", "0.0.0.0", "--port", "8080"]
