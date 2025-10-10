#!/bin/bash
#set -xv

WORKING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=/dev/null
source "${WORKING_DIR}/scripts/step-0-color.sh"

# shellcheck source=/dev/null
source "${WORKING_DIR}/scripts/step-1-os.sh"

export REPO_TAG=${REPO_TAG:-"1.2.0"}

# shellcheck source=./docs/build.sh
# echo "${WORKING_DIR}/docs/build.sh"

# shellcheck source=./scripts/run-python.sh
# echo "${WORKING_DIR}/scripts/run-python.sh"

# shellcheck source=./scripts/run-clean.sh
# ${WORKING_DIR}/scripts/run-clean.sh"

echo -e "${cyan} ${WORKING_DIR}/scripts/run-install.sh ${NC}"
"${WORKING_DIR}/scripts/run-install.sh"

#pipenv install

export TOX_TARGET=${TOX_TARGET:-"py312"} # tox --notest  # Pre-populate virtualenv use TOX_TARGET

#export PATH="${VIRTUALENV_PATH}/bin:${PATH}"
echo -e "${cyan} PATH : ${PATH} ${NC}"
#export PYTHONPATH="${VIRTUALENV_PATH}/lib/python${PYTHON_MAJOR_VERSION}/site-packages/"
echo -e "${cyan} PYTHONPATH : ${PYTHONPATH} ${NC}"

python -V || true

#setup-py-upgrade ./
# setup-cfg-fmt setup.cfg

#"${WORKING_DIR}/scripts/run-test.sh"

#git tag --delete v1.0.0
#git push --delete origin v1.0.0
echo -e "${magenta} git tag v${REPO_TAG} ${NC}"
echo -e "${magenta} git push origin --tags ${NC}"

#echo -e "${cyan} PACKAGE ${NC}"

python setup.py version

pytest --cache-clear --setup-show tests/test_nabla_version.py

#echo -e "${cyan} python setup.py sdist bdist_wheel ${NC}"
#python setup.py sdist bdist_wheel
#echo -e "${magenta} twine upload dist/* ${NC}"

exit 0
