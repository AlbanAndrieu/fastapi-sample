#!/bin/bash
set -xv

WORKING_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}"  )" && pwd  )"

# https://github.com/locustio/locust/wiki/Installation#increasing-maximum-number-of-open-files-limit
# https://www.tecmint.com/increase-set-open-file-limits-in-linux/
ulimit -Hn
ulimit -Sn

echo "sudo sysctl -w fs.file-max=500000"
cat /proc/sys/fs/file-max

# https://unix.stackexchange.com/questions/366352/etc-security-limits-conf-not-applied/443467#443467

locust -f ${WORKING_DIR}/../nabla/perf/locustfile.py

echo "Open http://localhost:8089/ on your browser"

exit 1
