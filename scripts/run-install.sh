#!/usr/bin/env bash
# shellcheck shell=bash

# shellcheck disable=SC2034
WORKING_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=./docs/build.sh
#echo "${WORKING_DIR}/docs/build.sh"

# shellcheck source=./scripts/run-python.sh
# echo "${WORKING_DIR}/scripts/run-python.sh"

#pip uninstall pylint pytest tox setup-cfg-fmt molecule yamllint pip-upgrade ansible

# source /opt/ansible/env38/bin/activate

echo -e "${magenta} python -m pipenv install --dev --site-packages --ignore-pipfile ${NC}"
python -m pipenv install --dev --site-packages --ignore-pipfile 2>/dev/null

echo -e "${magenta} pip install --upgrade pip ${NC}"

#pip install setup-py-upgrade
#pip install setup-cfg-fmt

echo -e "${magenta} pip install setuptools wheel twine ${NC}"

export POETRY_VERSION=${POETRY_VERSION:-"2.2.1"}

# echo -e "${cyan} poetry update ${NC}"
echo -e "${cyan} pip install poetry==${POETRY_VERSION} ${NC}"
pip install "poetry==${POETRY_VERSION}"

echo "===> 👉 ⛏️ 💎 poetry install --with format,test,extra,open_telemetry,api,api-legacy,deployment,influxdb,panda,temporal,utils,webui 💸 👈"
poetry install --with format,test,extra,open_telemetry,api,api-legacy,deployment,influxdb,panda,temporal,utils,webui

echo "===> 👉 poetry export -f requirements.txt --output requirements.txt --with api,deployment --without-hashes --without-urls --without dev"
poetry export -f requirements.txt --output requirements.txt --with api,deployment --without-hashes --without-urls --without dev

sudo apt-get install mypy

# os file watch limit reached uvicorn
sudo sysctl fs.inotify.max_user_watches=131070
sudo sysctl -p

exit 0
