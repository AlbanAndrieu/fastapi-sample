#!/bin/bash
TIMES=1
for i in $(eval echo "{1..$TIMES}");do
  siege -c 1 -r 10 http://localhost:8091/
  siege -c 3 -r 5 http://localhost:8091/demo/items/0
  siege -c 2 -r 3 http://0.0.0.0:8091/chain
  siege -c 3 -r 5 http://localhost:8091/v1/random
  siege -c 2 -r 3 http://0.0.0.0:8091/test/users/1
  siege -c 3 -r 5 http://localhost:8001/mcp
  siege -c 3 -r 5 http://localhost:8001/test/users/0
  siege -c 3 -r 5 http://localhost:8001/test/whoami
  siege -c 3 -r 5 http://127.0.0.1:8091/docs
  # siege -c 3 -r 5 http://127.0.0.1:8091/users/me
  sleep 5
done
exit 0
