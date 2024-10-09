#!/bin/bash
set -xv

WORKING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# https://github.com/locustio/locust/wiki/Installation#increasing-maximum-number-of-open-files-limit
# https://www.tecmint.com/increase-set-open-file-limits-in-linux/
ulimit -Hn
ulimit -Sn

echo "sudo sysctl -w fs.file-max=500000"
cat /proc/sys/fs/file-max

# https://unix.stackexchange.com/questions/366352/etc-security-limits-conf-not-applied/443467#443467

# https://medium.com/@mithun.kadyada/python-locust-for-load-testing-website-or-endpoint-url-b402eb3dbdf7
echo "locust -f \"${WORKING_DIR}/../nabla/perf/locustfile_jm.py\" --host==https://jm-ksdifu78gwc45gv1s0jshgtr764jnb79.lexsportiva.tech -c 1000 -r 100 --run-time 1h30m" # --no-web
locust -f "${WORKING_DIR}/../nabla/perf/locustfile_jm.py"

# locust -f "${WORKING_DIR}/../nabla/perf/locustfile_lra.py"

echo "Open http://localhost:8089/ on your browser"

# echo "Input : 5 - 2 - https://jm-frontnuxt.dev.int.jusmundi.com"
# echo "Input : 5 - 2 - https://back.service.gra.dev.consul:8089"

echo "Input : 5 - 2 - https://jm-ksdifu78gwc45gv1s0jshgtr764jnb79.lexsportiva.tech"
echo "Input : 5 - 2 - https://assistant-ksdifu78gwc45gv1s0jshgtr764jnb79.lexsportiva.tech"
echo "Input : 5 - 2 - http://fastapi-sample.service.gra.dev.consul/"

"${WORKING_DIR}/run-banned.sh"

exit 1
