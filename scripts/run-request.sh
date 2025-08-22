#!/bin/bash
#set -xv

TIMES=1
# shellcheck disable=SC2250,SC2034
for i in $(eval echo "{1..$TIMES}"); do
	siege -c 1 -r 10 http://localhost:8080/
	siege -c 3 -r 5 http://localhost:8080/v1/items/0
	#siege -c 3 -r 5 http://localhost:8080/io_task
	#siege -c 2 -r 5 http://localhost:8080/cpu_task
	#siege -c 2 -r 3 http://localhost:8080/chain
	#siege -c 1 -r 1 http://localhost:8080/error_test
	sleep 5
done

exit 0
