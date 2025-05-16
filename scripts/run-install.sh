#!/bin/bash
#set -xv

#WORKING_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}"  )" && pwd  )"

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

echo -e "${cyan} poetry update ${NC}"
#echo -e "${cyan} poetry install ${NC}"
poetry install

exit 0
