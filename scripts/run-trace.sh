#!/bin/bash
#set -xv

#pip3 install locust
locust -f locust.py --headless --users 10 --spawn-rate 1 -H http://localhost:8080

curl --request GET \
  --url http://localhost:8080/ \
  --header 'traceparent: 00-df853039b602c93e641526aaa7d67b8c-339f2b7a83c7d606-01'

exit 0
