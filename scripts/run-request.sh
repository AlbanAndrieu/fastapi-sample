#!/bin/bash
#set -xv

TIMES=1
# shellcheck disable=SC2250,SC2034
for i in $(eval echo "{1..$TIMES}"); do
  siege -c 1 -r 10 http://localhost:8091/
  siege -c 3 -r 5 http://localhost:8091/demo/items/0
  #siege -c 3 -r 5 http://localhost:8080/io_task
  #siege -c 2 -r 5 http://localhost:8080/cpu_task
  siege -c 2 -r 3 http://0.0.0.0:8091/chain
  #siege -c 1 -r 1 http://localhost:8080/error_test
  siege -c 3 -r 5 http://localhost:8091/v1/random
  siege -c 2 -r 3 http://0.0.0.0:8091/test/users/1
  siege -c 3 -r 5 http://localhost:8001/mcp
  siege -c 3 -r 5 http://localhost:8001/mcp/test/users/0
  siege -c 3 -r 5 http://127.0.0.1:8091/docs
  sleep 5
done

exit 0
