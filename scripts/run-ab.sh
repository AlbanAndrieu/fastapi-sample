#!/bin/bash

# Number of iterations
iterations=10

# ab test command
ab_command="ab -n 10000 -c 10000 http://localhost:8091/"

# Loop for the specified number of iterations
for ((i = 1; i <= iterations; i++)); do
  echo "Running test iteration ${i}"
  "${ab_command}"
done

exit 0
