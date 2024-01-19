#!/bin/bash

# Number of iterations
iterations=10

# ab test command
ab_command="ab -n 10000 -c 10000 http://10.30.0.115:20954/"

# Loop for the specified number of iterations
for ((i = 1; i <= iterations; i++)); do
  echo "Running test iteration ${i}"
  "$ab_command"
done
